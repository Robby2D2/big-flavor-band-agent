"""Unit tests for the radio playback clock and queue top-up logic.

These cover issue #5: the playback clock and queue top-up must run as standalone
work (driven by radio_background_loop) and must NOT be side-effects of reading
GET /api/radio/state. No live database or LLM is used here -- the queue top-up's
agent is replaced with a fake, and the playlist writer is stubbed out.
"""
import time

import pytest

import backend_api


@pytest.fixture(autouse=True)
def isolate_radio_state(monkeypatch):
    """Give each test a clean radio_state, no real playlist writes, no real agent."""
    monkeypatch.setattr(backend_api, "radio_state", {
        "current_song": None,
        "queue": [],
        "is_playing": False,
        "position": 0,
        "last_update": time.time(),
    })
    monkeypatch.setattr(backend_api, "active_listeners", {})
    monkeypatch.setattr(backend_api, "write_playlist_file", lambda: None)
    yield


def _song(song_id, duration=180):
    return {"id": song_id, "title": f"Song {song_id}", "duration": duration}


def test_update_position_advances_clock_while_playing():
    state = backend_api.radio_state
    state["current_song"] = _song(1, duration=180)
    state["is_playing"] = True
    state["position"] = 0
    state["last_update"] = time.time() - 5  # 5 seconds elapsed

    backend_api.update_radio_position()

    assert state["position"] >= 5
    assert state["current_song"]["id"] == 1  # not finished, no rollover


def test_update_position_rolls_over_to_next_song_when_finished():
    state = backend_api.radio_state
    state["current_song"] = _song(1, duration=10)
    state["queue"] = [_song(2), _song(3)]
    state["is_playing"] = True
    state["position"] = 0
    state["last_update"] = time.time() - 20  # past the 10s duration

    backend_api.update_radio_position()

    assert state["current_song"]["id"] == 2
    assert state["position"] == 0
    assert state["is_playing"] is True
    assert [s["id"] for s in state["queue"]] == [3]


def test_update_position_does_nothing_while_paused():
    state = backend_api.radio_state
    state["current_song"] = _song(1, duration=10)
    state["is_playing"] = False
    state["position"] = 0
    state["last_update"] = time.time() - 20

    backend_api.update_radio_position()

    assert state["position"] == 0
    assert state["current_song"]["id"] == 1  # paused clock never rolls over


@pytest.mark.asyncio
async def test_auto_populate_fills_queue_when_low(monkeypatch):
    class FakeAgent:
        async def search_songs(self, message, limit=10):
            return {"response": "ok", "songs": [_song(10), _song(11), _song(12)]}

    async def fake_get_agent():
        return FakeAgent()

    monkeypatch.setattr(backend_api, "get_agent", fake_get_agent)

    backend_api.radio_state["queue"] = []
    await backend_api.auto_populate_queue()

    assert [s["id"] for s in backend_api.radio_state["queue"]] == [10, 11, 12]


@pytest.mark.asyncio
async def test_auto_populate_skips_when_queue_full(monkeypatch):
    called = False

    async def fake_get_agent():
        nonlocal called
        called = True
        raise AssertionError("agent must not be called when queue is full")

    monkeypatch.setattr(backend_api, "get_agent", fake_get_agent)

    backend_api.radio_state["queue"] = [_song(i) for i in range(6)]
    await backend_api.auto_populate_queue()

    assert called is False
    assert len(backend_api.radio_state["queue"]) == 6


def test_cleanup_stale_listeners_does_not_pause_playback():
    """Removing the last listener must no longer stop the playback clock (issue #5)."""
    state = backend_api.radio_state
    state["current_song"] = _song(1)
    state["is_playing"] = True
    backend_api.active_listeners.clear()  # no listeners present

    backend_api.cleanup_stale_listeners()

    assert state["is_playing"] is True
