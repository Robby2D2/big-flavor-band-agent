"""Unit tests for the radio queue top-up driven by the background loop.

These cover issue #5: the queue top-up must run as standalone work (driven by
radio_background_loop) and must NOT be a side-effect of reading
GET /api/radio/state, nor gated on whether any listener is connected. No live
database or LLM is used here -- the top-up's agent is replaced with a fake, and the
playlist writer is stubbed out.

Radio state is process-external (issue #2): the helpers operate on a plain state
dict passed in by the caller (the background loop loads it from and saves it back
to the RadioStateStore), so these tests pass a local state dict rather than
mutating a module global.

The playback *clock* these tests used to cover is gone (issue #101). What is
playing is now reconciled against the stream itself, and those cases live in
tests/test_radio_on_air.py.
"""
import time

import pytest

import backend_api
from src.api import radio_service


@pytest.fixture(autouse=True)
def stub_playlist_writer(monkeypatch):
    """No real playlist writes.

    The queue helpers live in src.api.radio_service and call each other by that
    module's names, so patches must target radio_service (not the backend_api
    re-export) to intercept the internal calls.
    """
    monkeypatch.setattr(radio_service, "write_playlist_file", lambda *a, **k: None)
    yield


def _song(song_id, duration=180):
    return {"id": song_id, "title": f"Song {song_id}", "duration": duration}


def _state(**overrides):
    state = {
        "current_song": None,
        "queue": [],
        "is_playing": False,
        "position": 0,
        "last_update": time.time(),
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_auto_populate_fills_queue_when_low(monkeypatch):
    class FakeAgent:
        async def search_songs(self, message, limit=10):
            return {"response": "ok", "songs": [_song(10), _song(11), _song(12)]}

    async def fake_get_agent():
        return FakeAgent()

    monkeypatch.setattr(radio_service, "get_agent", fake_get_agent)

    state = _state(queue=[])
    await backend_api.auto_populate_queue(state)

    assert [s["id"] for s in state["queue"]] == [10, 11, 12]


@pytest.mark.asyncio
async def test_auto_populate_skips_when_queue_full(monkeypatch):
    called = False

    async def fake_get_agent():
        nonlocal called
        called = True
        raise AssertionError("agent must not be called when queue is full")

    monkeypatch.setattr(radio_service, "get_agent", fake_get_agent)

    state = _state(queue=[_song(i) for i in range(6)])
    await backend_api.auto_populate_queue(state)

    assert called is False
    assert len(state["queue"]) == 6


@pytest.mark.asyncio
async def test_top_up_runs_regardless_of_listeners(monkeypatch):
    """The top-up is owned by the background loop (issue #5) and takes no listener
    input, so a queue with nobody tuned in still refills."""
    class FakeAgent:
        async def search_songs(self, message, limit=10):
            return {"response": "ok", "songs": [_song(20)]}

    async def fake_get_agent():
        return FakeAgent()

    monkeypatch.setattr(radio_service, "get_agent", fake_get_agent)

    state = _state(queue=[], is_playing=True)
    await backend_api.auto_populate_queue(state)

    assert [s["id"] for s in state["queue"]] == [20]
