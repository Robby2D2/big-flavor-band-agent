"""Tests for the background Start analysis runner (src/api/analysis_jobs.py).

No DSP, no Demucs, no Postgres — fakes stand in for all three. What matters is
what the producer gets back after walking away: which stems a pass measures,
when it separates, and what is still there on return (PROD-11, PROD-22).
"""
import asyncio
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api import analysis_jobs as module  # noqa: E402
from src.api.analysis_jobs import (  # noqa: E402
    FULL_MIX_ROW_ID,
    MASTER_TOOLS,
    PER_STEM_TOOLS,
    STATUS_CANCELLED,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_IDLE,
    STATUS_RUNNING,
    AnalysisJobManager,
    PassServices,
    is_pitch_analyzable,
    stem_analysis_tools,
)

SONG = 1140
VERSION = 52


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch):
    monkeypatch.setattr(module, "SEPARATION_POLL_SECONDS", 0)


def stem(id_, name, instruments=None):
    return {
        "id": id_,
        "name": name,
        "display_name": None,
        "analysis_tools": stem_analysis_tools(name, instruments or []),
    }


def stem_set(id_, status="complete", version=VERSION):
    return {"id": id_, "status": status, "source_version_id": version, "error": None}


class FakeDb:
    def __init__(self, sets=()):
        self.sets = {s["id"]: dict(s) for s in sets}
        self.saved = None
        self.save_error = None

    async def list_stem_sets(self, song_id):
        return list(self.sets.values())

    async def get_stem_set(self, stem_set_id):
        return self.sets.get(stem_set_id)

    async def set_stem_set_status(self, stem_set_id, status, error=None):
        self.sets[stem_set_id]["status"] = status

    async def save_version_analysis(self, **row):
        if self.save_error:
            raise self.save_error
        self.saved = row

    async def get_version_analysis(self, version_id):
        if not self.saved or self.saved["version_id"] != version_id:
            return None
        return dict(self.saved)

    async def delete_failed_version_analysis(self, version_id):
        if self.saved and self.saved["status"] == STATUS_FAILED:
            self.saved = None


class Harness:
    """A manager wired to fakes that record what a pass asked for."""

    def __init__(self, db, stems_by_set=None, finish_separation=True, live_sets=()):
        self.db = db
        self.manager = AnalysisJobManager()
        self.stems_by_set = stems_by_set or {}
        self.measured = []
        self.separations = []
        self.completed = []
        self.finish_separation = finish_separation
        self.live_sets = set(live_sets)
        self.results = {}
        self.gate = None

    async def _measure(self, row_id, tool):
        self.measured.append((row_id, tool))
        if self.gate is not None and (row_id, tool) in self.gate["held"]:
            await self.gate["release"].wait()
        outcome = self.results.get(tool, {"recommended": False, "params": {}})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def _list_stems(self, stem_set_id):
        return self.stems_by_set.get(stem_set_id, [])

    async def _start_separation(self):
        new_id = max(self.db.sets, default=0) + 1
        self.separations.append(new_id)
        status = "complete" if self.finish_separation else "running"
        self.db.sets[new_id] = stem_set(new_id, status)
        self.live_sets.add(new_id)
        self.stems_by_set.setdefault(new_id, [stem(new_id * 100, "vocals")])
        return new_id

    @property
    def services(self):
        return PassServices(
            measure=self._measure,
            list_stems=self._list_stems,
            start_separation=self._start_separation,
            is_separating=lambda stem_set_id: stem_set_id in self.live_sets,
            on_complete=lambda rows, outcomes: self.completed.append((rows, outcomes)),
        )

    def start(self):
        return self.manager.start(SONG, VERSION, self.db, self.services)

    async def run(self):
        self.start()
        await self.manager._jobs[VERSION]["_task"]
        return await self.manager.status(VERSION, self.db)


# --- which tools a row gets -------------------------------------------------

def test_measures_pitch_on_a_vocal_stem_and_nothing_polyphonic():
    assert is_pitch_analyzable("vocals", [])
    assert not is_pitch_analyzable("drums", [])
    assert not is_pitch_analyzable("guitar", [])
    assert not is_pitch_analyzable("piano", [])


def test_leaves_the_bass_out_the_detector_cannot_hear_that_low():
    assert not is_pitch_analyzable("bass", [])


def test_follows_the_tagger_when_a_single_line_lands_inside_other():
    assert is_pitch_analyzable("other", [{"label": "Fiddle / violin", "score": 0.8}])
    assert not is_pitch_analyzable("other", [{"label": "Piano", "score": 0.8}])


def test_qualifies_on_any_tag_not_just_the_strongest():
    # Issue #91: a fiddle over a pad is tagged second and used to be skipped.
    assert is_pitch_analyzable(
        "other",
        [{"label": "Synthesizer", "score": 0.71}, {"label": "Fiddle / violin", "score": 0.64}],
    )


def test_pitch_is_added_to_the_tools_only_where_it_applies():
    assert stem_analysis_tools("vocals", []) == [*PER_STEM_TOOLS, "correct_pitch"]
    assert stem_analysis_tools("drums", []) == PER_STEM_TOOLS


def test_never_measures_tempo_there_is_no_correct_bpm_for_a_song():
    assert "match_tempo" not in MASTER_TOOLS
    assert "match_tempo" not in stem_analysis_tools("vocals", [])


# --- when a pass separates --------------------------------------------------

@pytest.mark.asyncio
async def test_reuses_existing_stems_instead_of_separating():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "vocals")]})
    result = await h.run()
    assert h.separations == []
    assert result["stem_set_id"] == 9


@pytest.mark.asyncio
async def test_ignores_a_complete_set_from_a_different_version():
    # Measuring another version's stems is the bug scoping exists to prevent.
    h = Harness(FakeDb([stem_set(9, version=51)]), {9: [stem(901, "vocals")]})
    await h.run()
    assert len(h.separations) == 1


@pytest.mark.asyncio
async def test_leaves_a_legacy_set_with_no_recorded_version_unattributed():
    h = Harness(FakeDb([stem_set(9, version=None)]), {9: [stem(901, "vocals")]})
    await h.run()
    assert len(h.separations) == 1


@pytest.mark.asyncio
async def test_separates_when_the_only_set_failed():
    h = Harness(FakeDb([stem_set(8, "failed")]))
    await h.run()
    assert len(h.separations) == 1


@pytest.mark.asyncio
async def test_waits_for_a_separation_already_running_rather_than_starting_another():
    db = FakeDb([stem_set(7, "running")])
    h = Harness(db, {7: [stem(701, "drums")]}, live_sets={7})
    h.start()
    await asyncio.sleep(0.01)
    assert h.separations == []
    assert (await h.manager.status(VERSION, db))["stage"] == module.STAGE_SEPARATING

    db.sets[7]["status"] = "complete"
    await h.manager._jobs[VERSION]["_task"]
    assert (await h.manager.status(VERSION, db))["stem_set_id"] == 7


@pytest.mark.asyncio
async def test_does_not_wait_on_a_set_a_restart_orphaned():
    # "running" in the DB with nothing working on it would be waited on forever.
    h = Harness(FakeDb([stem_set(7, "running")]))
    result = await h.run()
    assert len(h.separations) == 1
    assert result["status"] == STATUS_COMPLETE


# --- the pass and what it leaves behind -------------------------------------

@pytest.mark.asyncio
async def test_measures_the_full_mix_and_every_stem_with_their_own_tools():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "vocals"), stem(902, "drums")]})
    await h.run()
    assert sorted(t for r, t in h.measured if r == FULL_MIX_ROW_ID) == sorted(MASTER_TOOLS)
    assert ("correct_pitch" in [t for r, t in h.measured if r == 901])
    assert ("correct_pitch" not in [t for r, t in h.measured if r == 902])


@pytest.mark.asyncio
async def test_findings_are_there_after_the_job_has_left_memory():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    h.results["remove_hum"] = {"recommended": True, "params": {"fundamental_hz": 60}}

    result = await h.run()

    assert VERSION not in h.manager._jobs
    assert result["status"] == STATUS_COMPLETE
    assert {"row_id": 901, "tool": "remove_hum", "result": h.results["remove_hum"]} in result["outcomes"]


@pytest.mark.asyncio
async def test_progress_is_reported_while_measuring():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    release = asyncio.Event()
    h.gate = {"held": {(901, "remove_artifacts")}, "release": release}
    h.start()
    await asyncio.sleep(0.01)

    status = await h.manager.status(VERSION, h.db)
    assert status["status"] == STATUS_RUNNING
    assert status["stage"] == module.STAGE_MEASURING
    assert status["rows"][1]["label"] == "drums"
    assert status["rows"][1]["total"] == len(PER_STEM_TOOLS)
    assert status["rows"][1]["done"] == len(PER_STEM_TOOLS) - 1
    assert "outcomes" not in status

    release.set()
    await h.manager._jobs[VERSION]["_task"]


@pytest.mark.asyncio
async def test_a_second_start_joins_the_running_pass():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    release = asyncio.Event()
    h.gate = {"held": {(901, "remove_artifacts")}, "release": release}
    h.start()
    task = h.manager._jobs[VERSION]["_task"]
    h.start()
    assert h.manager._jobs[VERSION]["_task"] is task
    release.set()
    await task


@pytest.mark.asyncio
async def test_a_tool_that_fails_costs_that_check_not_the_pass():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    h.results["apply_eq"] = RuntimeError("librosa fell over")
    result = await h.run()
    assert result["status"] == STATUS_COMPLETE
    assert not any(o["tool"] == "apply_eq" for o in result["outcomes"])
    assert all(row["done"] == row["total"] for row in result["rows"])


@pytest.mark.asyncio
async def test_a_nan_measurement_cannot_break_the_save():
    # Postgres refuses NaN in JSONB; one bad number must not lose the pass.
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    h.results["remove_hum"] = {"recommended": True, "findings": {"snr": math.nan}}
    result = await h.run()
    assert result["status"] == STATUS_COMPLETE
    assert not any(o["tool"] == "remove_hum" for o in result["outcomes"])


@pytest.mark.asyncio
async def test_findings_stop_counting_once_the_version_is_re_separated():
    db = FakeDb([stem_set(9)])
    h = Harness(db, {9: [stem(901, "drums")]})
    await h.run()
    db.sets[10] = stem_set(10)
    assert (await h.manager.status(VERSION, db))["status"] == STATUS_IDLE


@pytest.mark.asyncio
async def test_a_new_set_for_another_version_does_not_retire_these_findings():
    db = FakeDb([stem_set(9)])
    h = Harness(db, {9: [stem(901, "drums")]})
    await h.run()
    db.sets[10] = stem_set(10, version=51)
    assert (await h.manager.status(VERSION, db))["status"] == STATUS_COMPLETE


@pytest.mark.asyncio
async def test_a_fresh_process_reads_the_stored_outcome():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    await h.run()
    assert (await AnalysisJobManager().status(VERSION, h.db))["status"] == STATUS_COMPLETE


@pytest.mark.asyncio
async def test_a_version_never_analyzed_is_idle():
    assert (await AnalysisJobManager().status(VERSION, FakeDb()))["status"] == STATUS_IDLE


@pytest.mark.asyncio
async def test_findings_survive_in_memory_when_the_save_fails():
    db = FakeDb([stem_set(9)])
    db.save_error = RuntimeError("connection reset")
    h = Harness(db, {9: [stem(901, "drums")]})
    result = await h.run()
    assert result["status"] == STATUS_COMPLETE
    assert "outcomes" in result


# --- finishing --------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_warm_render_starts_before_the_pass_reports_complete():
    # A poller that sees "complete" looks for the render at once.
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    seen = []
    services = h.services
    wrapped = PassServices(
        measure=services.measure,
        list_stems=services.list_stems,
        start_separation=services.start_separation,
        is_separating=services.is_separating,
        on_complete=lambda rows, outcomes: seen.append(h.manager._jobs[VERSION]["status"]),
    )
    h.manager.start(SONG, VERSION, h.db, wrapped)
    await h.manager._jobs[VERSION]["_task"]
    assert seen == [STATUS_RUNNING]


@pytest.mark.asyncio
async def test_a_warm_render_that_will_not_start_does_not_fail_the_pass():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    services = h.services

    def boom(rows, outcomes):
        raise RuntimeError("already rendering")

    wrapped = PassServices(
        measure=services.measure,
        list_stems=services.list_stems,
        start_separation=services.start_separation,
        is_separating=services.is_separating,
        on_complete=boom,
    )
    h.manager.start(SONG, VERSION, h.db, wrapped)
    await h.manager._jobs[VERSION]["_task"]
    assert (await h.manager.status(VERSION, h.db))["status"] == STATUS_COMPLETE


@pytest.mark.asyncio
async def test_a_failed_separation_is_reported_and_can_be_dismissed():
    db = FakeDb([stem_set(7, "running")])
    db.sets[7]["error"] = "Demucs ran out of memory"
    h = Harness(db, live_sets={7})
    h.start()
    await asyncio.sleep(0.01)
    db.sets[7]["status"] = "failed"
    await h.manager._jobs[VERSION]["_task"]

    status = await h.manager.status(VERSION, db)
    assert status["status"] == STATUS_FAILED
    assert status["error"] == "Demucs ran out of memory"
    assert status["rows"] == []
    assert h.completed == []

    await h.manager.dismiss_failure(VERSION, db)
    assert (await h.manager.status(VERSION, db))["status"] == STATUS_IDLE


@pytest.mark.asyncio
async def test_dismiss_never_forgets_findings():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    await h.run()
    await h.manager.dismiss_failure(VERSION, h.db)
    assert (await h.manager.status(VERSION, h.db))["status"] == STATUS_COMPLETE


# --- cancelling (PROD-19) ---------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_keeps_only_rows_measured_whole():
    h = Harness(FakeDb([stem_set(9)]), {9: [stem(901, "drums")]})
    h.results["remove_hum"] = {"recommended": True, "params": {}}
    h.results["trim_silence"] = {"recommended": True, "params": {}}
    release = asyncio.Event()
    h.gate = {"held": {(901, "remove_artifacts")}, "release": release}
    h.start()
    await asyncio.sleep(0.01)

    await h.manager.cancel(VERSION, h.db)
    await h.manager._jobs[VERSION]["_task"]

    status = await h.manager.status(VERSION, h.db)
    assert status["status"] == STATUS_CANCELLED
    # The half-measured stem would otherwise read as clean.
    assert {o["row_id"] for o in status["outcomes"]} == {FULL_MIX_ROW_ID}
    assert h.completed == []


@pytest.mark.asyncio
async def test_cancel_during_separation_cancels_the_separation():
    db = FakeDb([stem_set(7, "running")])
    h = Harness(db, live_sets={7})
    h.start()
    await asyncio.sleep(0.01)

    await h.manager.cancel(VERSION, db)
    await h.manager._jobs[VERSION]["_task"]

    assert db.sets[7]["status"] == STATUS_CANCELLED
    assert (await h.manager.status(VERSION, db))["status"] == STATUS_CANCELLED


@pytest.mark.asyncio
async def test_cancel_with_nothing_running_is_refused():
    with pytest.raises(ValueError):
        await AnalysisJobManager().cancel(VERSION, FakeDb())


# --- the render a pass sets off ---------------------------------------------

def test_warm_render_matches_the_fingerprint_of_the_pages_own_payload(monkeypatch):
    """Save is only instant when the page's payload lands on this render."""
    from src.api.routers import produce

    captured = {}

    def fake_start(song_id, preview, fix_count, render, fingerprint):
        captured.update(preview=preview, fix_count=fix_count, fingerprint=fingerprint)

    monkeypatch.setattr(produce.accept_jobs, "start", fake_start)
    monkeypatch.setattr(produce.accept_jobs, "is_running", lambda song_id: False)
    monkeypatch.setattr(produce.accept_jobs, "cached_render", lambda song_id, print_: None)

    rows = [
        {"row_id": FULL_MIX_ROW_ID, "label": "Full mix", "done": 5, "total": 5},
        {"row_id": 901, "label": "bass", "done": 5, "total": 5},
        {"row_id": 902, "label": "drums", "done": 5, "total": 5},
    ]
    outcomes = [
        {"row_id": FULL_MIX_ROW_ID, "tool": "normalize_audio", "result": {"recommended": True, "params": {"target_db": -14}}},
        {"row_id": 901, "tool": "apply_eq", "result": {"recommended": False, "params": {"low_gain_db": -3}}},
        {"row_id": 902, "tool": "remove_hum", "result": {"recommended": True, "params": {"fundamental_hz": 60}}},
    ]
    produce._warm_analyzed_render(SONG, VERSION, rows, outcomes, agent=None, db=None)

    # Exactly what buildAcceptPayload posts: every stem, only recommended fixes.
    page_payload = produce.AcceptFixesRequest(
        song_id=SONG,
        source_version_id=VERSION,
        stems=[
            {"stem_id": 901, "fixes": []},
            {"stem_id": 902, "fixes": [{"tool": "remove_hum", "params": {"fundamental_hz": 60}}]},
        ],
        master_fixes=[{"tool": "normalize_audio", "params": {"target_db": -14}}],
        preview=False,
    )
    assert captured["fingerprint"] == produce._accept_fingerprint(page_payload)
    assert captured["preview"] is True
    assert captured["fix_count"] == 2


def test_warm_render_reports_a_cached_mix_rather_than_rendering_again(monkeypatch):
    from src.api.routers import produce

    done = {}
    monkeypatch.setattr(produce.accept_jobs, "is_running", lambda song_id: False)
    monkeypatch.setattr(produce.accept_jobs, "cached_render", lambda song_id, print_: "/tmp/mix.wav")
    monkeypatch.setattr(produce.accept_jobs, "cached_notices", lambda song_id, print_: [])
    monkeypatch.setattr(
        produce.accept_jobs, "complete_now",
        lambda song_id, preview, fix_count, result: done.update(result),
    )
    monkeypatch.setattr(
        produce.accept_jobs, "start",
        lambda *a, **k: pytest.fail("rendered a mix it already had"),
    )
    produce._warm_analyzed_render(SONG, VERSION, [], [], agent=None, db=None)
    assert done["candidate_path"] == "/tmp/mix.wav"


def test_warm_render_leaves_a_running_render_alone(monkeypatch):
    from src.api.routers import produce

    monkeypatch.setattr(produce.accept_jobs, "is_running", lambda song_id: True)
    monkeypatch.setattr(
        produce.accept_jobs, "start",
        lambda *a, **k: pytest.fail("started a second render"),
    )
    produce._warm_analyzed_render(SONG, VERSION, [], [], agent=None, db=None)
