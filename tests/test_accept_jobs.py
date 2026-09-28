"""Tests for the background accept-fixes render manager (src/api/accept_jobs.py).

No DSP, no DB — a fake render coroutine stands in for the minutes of audio work.
What matters here is the bookkeeping that keeps a producer from waiting on a
render twice: the fingerprint that decides when a render can be reused, and the
job lifecycle the page polls.
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.accept_jobs import (  # noqa: E402
    RESULT_TTL_SECONDS,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_IDLE,
    STATUS_RUNNING,
    AcceptJobManager,
    fingerprint,
)

SONG = 880


def payload(**overrides):
    base = {
        "song_id": SONG,
        "source_version_id": 3,
        "stems": [{"stem_id": 1, "fixes": [{"tool": "reduce_noise", "params": {"amount": 0.5}}]}],
        "master_fixes": [{"tool": "normalize_audio", "params": {}}],
    }
    base.update(overrides)
    return base


# --- the fingerprint ------------------------------------------------------

def test_same_fix_set_fingerprints_the_same():
    assert fingerprint(payload()) == fingerprint(payload())


def test_key_order_does_not_change_the_fingerprint():
    a = {"song_id": 1, "master_fixes": []}
    b = {"master_fixes": [], "song_id": 1}
    assert fingerprint(a) == fingerprint(b)


def test_changed_params_change_the_fingerprint():
    changed = payload(master_fixes=[{"tool": "normalize_audio", "params": {"target_db": -14}}])
    assert fingerprint(changed) != fingerprint(payload())


def test_changed_source_version_changes_the_fingerprint():
    assert fingerprint(payload(source_version_id=4)) != fingerprint(payload())


def test_dropping_a_fix_changes_the_fingerprint():
    assert fingerprint(payload(master_fixes=[])) != fingerprint(payload())


# --- the reuse cache ------------------------------------------------------

def test_cached_render_returns_the_file_for_a_matching_fingerprint(tmp_path):
    rendered = tmp_path / "mix.wav"
    rendered.write_bytes(b"audio")
    manager = AcceptJobManager()
    manager.remember_render(SONG, "abc", str(rendered))

    assert manager.cached_render(SONG, "abc") == str(rendered)


def test_a_different_fingerprint_is_not_a_hit(tmp_path):
    rendered = tmp_path / "mix.wav"
    rendered.write_bytes(b"audio")
    manager = AcceptJobManager()
    manager.remember_render(SONG, "abc", str(rendered))

    assert manager.cached_render(SONG, "different") is None


def test_a_render_whose_file_vanished_is_not_a_hit(tmp_path):
    """Rendered mixes live on disk; a cleaned-up file must force a fresh render."""
    rendered = tmp_path / "mix.wav"
    rendered.write_bytes(b"audio")
    manager = AcceptJobManager()
    manager.remember_render(SONG, "abc", str(rendered))
    os.remove(rendered)

    assert manager.cached_render(SONG, "abc") is None
    # ...and the dead entry is forgotten rather than re-checked forever.
    assert manager.cached_render(SONG, "abc") is None


def test_another_song_is_not_a_hit(tmp_path):
    rendered = tmp_path / "mix.wav"
    rendered.write_bytes(b"audio")
    manager = AcceptJobManager()
    manager.remember_render(SONG, "abc", str(rendered))

    assert manager.cached_render(SONG + 1, "abc") is None


# --- the job lifecycle ----------------------------------------------------

def test_a_song_with_no_render_is_idle():
    assert AcceptJobManager().status(SONG)["status"] == STATUS_IDLE


@pytest.mark.asyncio
async def test_a_render_runs_and_reports_its_version():
    manager = AcceptJobManager()

    async def render():
        await asyncio.sleep(0)
        return {"version": {"version_id": 42}}

    started = manager.start(SONG, preview=False, fix_count=17, render=render)
    assert started["status"] == STATUS_RUNNING
    assert started["fix_count"] == 17
    assert manager.is_running(SONG)

    await asyncio.sleep(0.05)

    done = manager.status(SONG)
    assert done["status"] == STATUS_COMPLETE
    assert done["version"] == {"version_id": 42}
    assert not manager.is_running(SONG)


@pytest.mark.asyncio
async def test_a_failed_render_is_visible_to_the_poller():
    manager = AcceptJobManager()

    async def render():
        raise RuntimeError("ffmpeg fell over")

    manager.start(SONG, preview=False, fix_count=1, render=render)
    await asyncio.sleep(0.05)

    status = manager.status(SONG)
    assert status["status"] == STATUS_FAILED
    assert "ffmpeg fell over" in status["error"]


@pytest.mark.asyncio
async def test_an_http_error_reports_its_detail_not_its_status_code():
    """HTTPException str() is the code alone, which tells a producer nothing."""
    from fastapi import HTTPException

    manager = AcceptJobManager()

    async def render():
        raise HTTPException(status_code=404, detail="Stem 7 not found for this song")

    manager.start(SONG, preview=False, fix_count=1, render=render)
    await asyncio.sleep(0.05)

    assert manager.status(SONG)["error"] == "Stem 7 not found for this song"


@pytest.mark.asyncio
async def test_two_renders_for_one_song_do_not_overlap():
    manager = AcceptJobManager()

    async def render():
        await asyncio.sleep(0.2)
        return {"version": {"version_id": 1}}

    manager.start(SONG, preview=False, fix_count=1, render=render)
    with pytest.raises(RuntimeError):
        manager.start(SONG, preview=False, fix_count=1, render=render)


def test_complete_now_records_a_reused_render():
    manager = AcceptJobManager()
    status = manager.complete_now(
        SONG, preview=False, fix_count=17, result={"version": {"version_id": 9}}
    )

    assert status["status"] == STATUS_COMPLETE
    assert status["reused"] is True
    assert status["version"] == {"version_id": 9}


def test_clear_forgets_a_finished_job():
    manager = AcceptJobManager()
    manager.complete_now(SONG, preview=True, fix_count=1, result={"candidate_path": "/tmp/x.wav"})
    manager.clear(SONG)

    assert manager.status(SONG)["status"] == STATUS_IDLE


@pytest.mark.asyncio
async def test_clear_leaves_a_running_job_alone():
    manager = AcceptJobManager()

    async def render():
        await asyncio.sleep(0.2)
        return {}

    manager.start(SONG, preview=False, fix_count=1, render=render)
    manager.clear(SONG)

    assert manager.status(SONG)["status"] == STATUS_RUNNING


def test_a_stale_result_expires_back_to_idle(monkeypatch):
    manager = AcceptJobManager()
    manager.complete_now(SONG, preview=True, fix_count=1, result={"candidate_path": "/tmp/x.wav"})

    # Replace the module's `time` reference rather than time.time itself, which
    # is shared globally and would recurse into the stub.
    later = time.time() + RESULT_TTL_SECONDS + 60

    class FrozenClock:
        @staticmethod
        def time():
            return later

    monkeypatch.setattr("src.api.accept_jobs.time", FrozenClock)
    assert manager.status(SONG)["status"] == STATUS_IDLE


def test_a_finished_render_outlives_a_working_session():
    """The versions list keeps a row for the unsaved mix; it must not vanish."""
    assert RESULT_TTL_SECONDS >= 4 * 60 * 60


# --- several fix sets per song (the eviction that caused a second render) ----

def test_a_later_render_does_not_evict_an_earlier_fix_set(tmp_path):
    """A master-only preview used to replace the whole-queue render outright,
    so the Save that followed missed the cache and rendered 21 fixes again."""
    queue = tmp_path / "queue.wav"
    queue.write_bytes(b"a")
    master_only = tmp_path / "master.wav"
    master_only.write_bytes(b"b")
    manager = AcceptJobManager()

    manager.remember_render(SONG, "whole-queue", str(queue), stems=[{"name": "vocals"}])
    manager.remember_render(SONG, "master-only", str(master_only))

    assert manager.cached_render(SONG, "whole-queue") == str(queue)
    assert manager.cached_stems(SONG, "whole-queue") == [{"name": "vocals"}]


def test_the_oldest_fix_set_goes_first_when_the_song_is_full(tmp_path):
    from src.api.accept_jobs import RENDERS_PER_SONG

    manager = AcceptJobManager()
    for i in range(RENDERS_PER_SONG + 1):
        path = tmp_path / f"{i}.wav"
        path.write_bytes(b"x")
        manager.remember_render(SONG, f"print-{i}", str(path))

    assert manager.cached_render(SONG, "print-0") is None
    assert manager.cached_render(SONG, f"print-{RENDERS_PER_SONG}") is not None


# --- the chain cache -------------------------------------------------------

def test_a_chain_is_found_by_its_source_and_fixes(tmp_path):
    from src.api.accept_jobs import ChainCache

    rendered = tmp_path / "vocals.wav"
    rendered.write_bytes(b"x")
    cache = ChainCache()
    chain = [{"tool": "reduce_noise", "params": {"amount": 0.5}}]
    cache.put(ChainCache.key("/stems/vocals.wav", chain), str(rendered), [{"tool": "t"}])

    hit = cache.get(ChainCache.key("/stems/vocals.wav", chain))
    assert hit == {"path": str(rendered), "notices": [{"tool": "t"}]}
    assert cache.get(ChainCache.key("/stems/drums.wav", chain)) is None
    changed = [{"tool": "reduce_noise", "params": {"amount": 0.6}}]
    assert cache.get(ChainCache.key("/stems/vocals.wav", changed)) is None


def test_a_chain_whose_file_vanished_is_a_miss(tmp_path):
    from src.api.accept_jobs import ChainCache

    cache = ChainCache()
    cache.put("k", str(tmp_path / "gone.wav"))
    assert cache.get("k") is None


def test_the_chain_cache_is_bounded(tmp_path):
    from src.api.accept_jobs import ChainCache

    cache = ChainCache(size=2)
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.wav"
        path.write_bytes(b"x")
        cache.put(name, str(path))

    assert cache.get("a") is None
    assert cache.get("c") is not None


# --- progress, cancel, save-when-ready (PROD-19) ----------------------------

@pytest.mark.asyncio
async def test_progress_is_visible_while_the_render_runs():
    manager = AcceptJobManager()
    gate = asyncio.Event()

    async def render():
        manager.report(SONG, stage="stems", stem="vocals", tool="reduce_noise", done=3, total=21)
        await gate.wait()
        return {"candidate_path": "/tmp/x.wav"}

    manager.start(SONG, preview=True, fix_count=21, render=render)
    await asyncio.sleep(0.01)

    progress = manager.status(SONG)["progress"]
    assert progress == {"stage": "stems", "stem": "vocals", "tool": "reduce_noise",
                        "done": 3, "total": 21}
    gate.set()


@pytest.mark.asyncio
async def test_a_cancelled_render_stops_and_says_so():
    from src.api.accept_jobs import STATUS_CANCELLED

    manager = AcceptJobManager()
    finished = []

    async def render():
        await asyncio.sleep(5)
        finished.append(True)
        return {}

    manager.start(SONG, preview=True, fix_count=3, render=render)
    await asyncio.sleep(0.01)
    manager.cancel(SONG)
    await asyncio.sleep(0.05)

    assert manager.status(SONG)["status"] == STATUS_CANCELLED
    assert finished == []
    assert not manager.is_running(SONG)


@pytest.mark.asyncio
async def test_a_render_between_steps_stops_at_the_next_one():
    """A tool on a thread cannot be interrupted; the next step is where it ends."""
    from src.api.accept_jobs import STATUS_CANCELLED

    manager = AcceptJobManager()
    steps = []

    async def render():
        for step in range(3):
            manager.report(SONG, done=step)
            steps.append(step)
            if step == 0:
                manager._jobs[SONG]["_cancelled"] = True  # cancel lands mid-step
        return {}

    manager.start(SONG, preview=True, fix_count=3, render=render)
    await asyncio.sleep(0.05)

    assert steps == [0]
    assert manager.status(SONG)["status"] == STATUS_CANCELLED


@pytest.mark.asyncio
async def test_cancel_is_refused_while_the_version_is_written():
    manager = AcceptJobManager()
    gate = asyncio.Event()

    async def render():
        manager.report(SONG, stage="saving")
        await gate.wait()
        return {"version": {"version_id": 1}}

    manager.start(SONG, preview=False, fix_count=1, render=render)
    await asyncio.sleep(0.01)

    with pytest.raises(ValueError):
        manager.cancel(SONG)
    gate.set()
    await asyncio.sleep(0.01)
    assert manager.status(SONG)["status"] == STATUS_COMPLETE


def test_there_is_nothing_to_cancel_when_idle():
    with pytest.raises(ValueError):
        AcceptJobManager().cancel(SONG)


@pytest.mark.asyncio
async def test_a_save_rides_on_the_running_render_of_the_same_fixes():
    manager = AcceptJobManager()
    gate = asyncio.Event()
    saved = []

    async def render():
        await gate.wait()
        return {"candidate_path": "/tmp/mix.wav", "notices": []}

    async def save(result):
        saved.append(result["candidate_path"])
        return {"version": {"version_id": 77}}

    manager.start(SONG, preview=True, fix_count=21, render=render, fingerprint="abc")
    assert manager.attach_save(SONG, "other-fixes", save) is None
    attached = manager.attach_save(SONG, "abc", save)
    assert attached["preview"] is False
    assert "_then_save" not in attached, "bookkeeping never reaches the browser"

    gate.set()
    await asyncio.sleep(0.02)

    done = manager.status(SONG)
    assert saved == ["/tmp/mix.wav"]
    assert done["status"] == STATUS_COMPLETE
    assert done["version"] == {"version_id": 77}


@pytest.mark.asyncio
async def test_cancelling_only_the_save_keeps_the_render():
    manager = AcceptJobManager()
    gate = asyncio.Event()
    saved = []

    async def render():
        await gate.wait()
        return {"candidate_path": "/tmp/mix.wav"}

    async def save(result):
        saved.append(result)
        return {"version": {"version_id": 1}}

    manager.start(SONG, preview=True, fix_count=2, render=render, fingerprint="abc")
    manager.attach_save(SONG, "abc", save)
    manager.cancel(SONG, save_only=True)
    gate.set()
    await asyncio.sleep(0.02)

    done = manager.status(SONG)
    assert saved == []
    assert done["status"] == STATUS_COMPLETE
    assert done["preview"] is True
    assert done["candidate_path"] == "/tmp/mix.wav"
