"""Fixes render once — on Start analysis — and every later path reuses them.

The live log that started this: Start analysis rendered 21 fixes; pressing play
rendered every stem's chain again through ``preview-chain``; and a master-only
preview for the full-mix row then evicted the whole-queue render, so the next
save rendered all 21 a third time. These drive the real ``_render_mix`` and the
preview routes' shared ``_cached_chain`` with a fake agent that counts tool
calls, and a fresh chain cache per test.
"""
from pathlib import Path

import pytest

from src.api import accept_jobs as accept_jobs_module
from src.api import stem_jobs
from src.api.routers import produce


class CountingAgent:
    """Writes each tool's output file and records the call."""

    def __init__(self):
        self.calls = []

    async def execute_tool(self, tool, args):
        self.calls.append((tool, Path(args["file_path"]).name))
        Path(args["output_path"]).write_bytes(f"after-{tool}".encode())
        return {"status": "success"}


class FakeDB:
    def __init__(self, stems):
        self._stems = stems

    async def get_stem(self, stem_id):
        return self._stems.get(stem_id)

    async def get_stem_set(self, stem_set_id):
        return {"id": stem_set_id, "song_id": 7, "model": "htdemucs_6s"}


@pytest.fixture
def rig(tmp_path, monkeypatch):
    produced = tmp_path / "produced"
    monkeypatch.setattr(produce, "_produced_dir", lambda: produced)
    monkeypatch.setattr(produce, "chain_cache", accept_jobs_module.ChainCache())

    remixes = []

    def fake_remix(parts, output, gains):
        remixes.append([part["path"] for part in parts])
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"downmix")

    monkeypatch.setattr(produce.stem_separation, "remix_stems", fake_remix)

    copies = []

    def fake_preview(source, output):
        copies.append(Path(source).name)
        return output

    monkeypatch.setattr(produce.audio_preview, "build_preview", fake_preview)

    stems = {}
    for stem_id, name in ((1, "vocals"), (2, "drums")):
        path = tmp_path / f"{name}.wav"
        path.write_bytes(name.encode())
        stems[stem_id] = {"id": stem_id, "stem_set_id": 9, "name": name, "path": str(path)}
    agent = CountingAgent()
    agent.copies = copies  # the playback copies the render asked for
    return agent, FakeDB(stems), remixes


def queue(vocal_amount=0.5):
    return produce.AcceptFixesRequest(
        song_id=7,
        source_version_id=3,
        stems=[
            produce.StemAcceptSpec(stem_id=1, fixes=[
                produce.StemFixSpec(tool="reduce_noise", params={"amount": vocal_amount}),
                produce.StemFixSpec(tool="de_ess"),
            ]),
            produce.StemAcceptSpec(stem_id=2, fixes=[produce.StemFixSpec(tool="apply_eq")]),
        ],
        master_fixes=[produce.StemFixSpec(tool="normalize_audio")],
        preview=True,
    )


@pytest.mark.asyncio
async def test_the_same_queue_renders_once(rig):
    agent, db, remixes = rig

    first, *_ = await produce._render_mix(queue(), agent, db)
    calls_after_first = len(agent.calls)
    second, *_ = await produce._render_mix(queue(), agent, db)

    assert calls_after_first == 4  # 2 vocal fixes, 1 drum fix, 1 master fix
    assert len(agent.calls) == 4, "a second render of the same queue runs no tools"
    assert len(remixes) == 1
    assert second == first


@pytest.mark.asyncio
async def test_changing_one_stem_renders_that_stem_alone(rig):
    agent, db, remixes = rig
    await produce._render_mix(queue(), agent, db)
    agent.calls.clear()

    await produce._render_mix(queue(vocal_amount=0.8), agent, db)

    # The vocals chain again, then the remix and master (their inputs changed);
    # the drums chain is reused untouched.
    assert [tool for tool, _ in agent.calls] == ["reduce_noise", "de_ess", "normalize_audio"]
    assert len(remixes) == 2


@pytest.mark.asyncio
async def test_play_after_analysis_reuses_the_rendered_stem(rig):
    """preview-chain and the whole-queue render share one cache."""
    agent, db, _ = rig
    await produce._render_mix(queue(), agent, db)
    agent.calls.clear()

    vocals = db._stems[1]
    path, _notices = await produce._cached_chain(
        agent, queue().stems[0].fixes, Path(vocals["path"]), Path("unused"), tag="run1",
    )

    assert agent.calls == []
    assert path.read_bytes() == b"after-de_ess"


@pytest.mark.asyncio
async def test_progress_counts_every_fix_and_says_where_it_is(rig):
    agent, db, _ = rig
    seen = []

    await produce._render_mix(queue(), agent, db, report=lambda **f: seen.append(f))

    tools = [f["tool"] for f in seen if f.get("tool")]
    assert tools == ["reduce_noise", "de_ess", "apply_eq", "normalize_audio"]
    assert [f["done"] for f in seen if f.get("tool")] == [0, 1, 2, 3]
    assert seen[0]["stem"] == "vocals" and seen[0]["total"] == 4
    assert seen[0]["stems_total"] == 2
    assert any(f["stage"] == "remix" for f in seen)
    assert [f["done"] for f in seen if f.get("stage") == "master"][-1] == 4
    # The last stage makes the compressed copies the console will play.
    assert seen[-1]["stage"] == "playback"
    assert (seen[-1]["playback_done"], seen[-1]["playback_total"]) == (2, 2)


@pytest.mark.asyncio
async def test_a_cached_rerender_still_reaches_the_end_of_its_count(rig):
    agent, db, _ = rig
    await produce._render_mix(queue(), agent, db)
    seen = []

    await produce._render_mix(queue(), agent, db, report=lambda **f: seen.append(f))

    master = [f for f in seen if f.get("stage") == "master"][-1]
    assert master["done"] == master["total"] == 4


@pytest.mark.asyncio
async def test_a_cancelled_render_keeps_the_chains_it_finished(rig):
    """Cancel stops at the next step; what was already rendered stays cached,
    so the next render resumes rather than starting over."""
    agent, db, _ = rig

    def report(**fields):
        if fields.get("stem") == "drums":
            raise accept_jobs_module.RenderCancelled()

    with pytest.raises(accept_jobs_module.RenderCancelled):
        await produce._render_mix(queue(), agent, db, report=report)
    agent.calls.clear()

    await produce._render_mix(queue(), agent, db)

    assert [tool for tool, _ in agent.calls] == ["apply_eq", "normalize_audio"]


# --- separation cancel -------------------------------------------------------

class StemSetDB:
    def __init__(self, status):
        self.status = status
        self.added = []

    async def get_stem_set(self, stem_set_id):
        return {"id": stem_set_id, "status": self.status}

    async def set_stem_set_status(self, stem_set_id, status, error=None):
        self.status = status

    async def add_stem(self, *args):
        self.added.append(args)
        return {"id": len(self.added)}


@pytest.mark.asyncio
async def test_a_separation_cancelled_mid_run_discards_its_output(tmp_path, monkeypatch):
    output = tmp_path / "stems"
    db = StemSetDB("queued")

    def fake_separate(source, out, model):
        # The producer cancels while Demucs is running on its thread.
        db.status = stem_jobs.STATUS_CANCELLED
        Path(out).mkdir(parents=True)
        (Path(out) / "vocals.wav").write_bytes(b"x")
        return [{"name": "vocals", "path": str(Path(out) / "vocals.wav")}]

    monkeypatch.setattr(stem_jobs.stem_separation, "separate_stems", fake_separate)

    await stem_jobs.StemJobManager()._run(5, "song.wav", str(output), "htdemucs_6s", db)

    assert db.status == stem_jobs.STATUS_CANCELLED
    assert db.added == [], "a cancelled set gets no stems"
    assert not output.exists()


@pytest.mark.asyncio
async def test_a_separation_cancelled_before_it_starts_never_runs(tmp_path, monkeypatch):
    db = StemSetDB(stem_jobs.STATUS_CANCELLED)

    def never(*args):
        raise AssertionError("Demucs must not start for a cancelled set")

    monkeypatch.setattr(stem_jobs.stem_separation, "separate_stems", never)

    await stem_jobs.StemJobManager()._run(5, "song.wav", str(tmp_path / "s"), "m", db)

    assert db.status == stem_jobs.STATUS_CANCELLED


@pytest.mark.asyncio
async def test_every_fixed_stem_gets_a_playback_copy(rig):
    """The console used to download each fixed stem as a ~23 MB WAV."""
    agent, db, _ = rig

    await produce._render_mix(queue(), agent, db)

    # One per fixed stem, made from that stem's final file.
    assert agent.copies[0].startswith("01_de_ess_")
    assert agent.copies[1].startswith("00_apply_eq_")


@pytest.mark.asyncio
async def test_a_chain_keeps_only_its_final_file(rig, tmp_path):
    agent, db, _ = rig
    source = tmp_path / "vocals.wav"

    final, _ = await produce._chain_apply_tools(
        agent, queue().stems[0].fixes, source, tmp_path / "out", tag="vocals"
    )

    assert [f.name for f in (tmp_path / "out" / "vocals").iterdir()] == [final.name]
    assert source.exists(), "the source is never deleted"


@pytest.mark.asyncio
async def test_a_cancelled_chain_leaves_nothing_behind(rig, tmp_path):
    agent, _db, _ = rig
    calls = []

    def on_step(tool):
        calls.append(tool)
        if len(calls) == 2:
            raise accept_jobs_module.RenderCancelled()

    with pytest.raises(accept_jobs_module.RenderCancelled):
        await produce._chain_apply_tools(
            agent, queue().stems[0].fixes, tmp_path / "vocals.wav", tmp_path / "out",
            tag="vocals", on_step=on_step,
        )

    assert list((tmp_path / "out" / "vocals").iterdir()) == []
