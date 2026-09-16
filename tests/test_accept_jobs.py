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
    later = time.time() + 60 * 60

    class FrozenClock:
        @staticmethod
        def time():
            return later

    monkeypatch.setattr("src.api.accept_jobs.time", FrozenClock)
    assert manager.status(SONG)["status"] == STATUS_IDLE
