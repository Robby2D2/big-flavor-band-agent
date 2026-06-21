"""Unit tests for the radio playback clock and queue top-up logic.

These cover issue #5: the playback clock and queue top-up must run as standalone
work (driven by radio_background_loop) and must NOT be side-effects of reading
GET /api/radio/state, nor gated on whether any listener is connected. No live
database or LLM is used here -- the queue top-up's agent is replaced with a fake,
and the playlist writer is stubbed out.

Radio state is now process-external (issue #2): the clock/top-up helpers operate
on a plain state dict passed in by the caller (the background loop loads it from
and saves it back to the RadioStateStore), so these tests pass a local state dict
rather than mutating a module global.
"""
import time

import pytest

import backend_api


@pytest.fixture(autouse=True)
def stub_playlist_writer(monkeypatch):
    """No real playlist writes; advance_to_next_song calls write_playlist_file(state)."""
    monkeypatch.setattr(backend_api, "write_playlist_file", lambda *a, **k: None)
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


def test_update_position_advances_clock_while_playing():
    state = _state(current_song=_song(1, duration=180), is_playing=True,
                   position=0, last_update=time.time() - 5)  # 5 seconds elapsed

    backend_api.update_radio_position(state)

    assert state["position"] >= 5
    assert state["current_song"]["id"] == 1  # not finished, no rollover


def test_update_position_rolls_over_to_next_song_when_finished():
    state = _state(current_song=_song(1, duration=10), queue=[_song(2), _song(3)],
                   is_playing=True, position=0, last_update=time.time() - 20)

    backend_api.update_radio_position(state)

    assert state["current_song"]["id"] == 2
    assert state["position"] == 0
    assert state["is_playing"] is True
    assert [s["id"] for s in state["queue"]] == [3]


def test_update_position_does_nothing_while_paused():
    state = _state(current_song=_song(1, duration=10), is_playing=False,
                   position=0, last_update=time.time() - 20)

    backend_api.update_radio_position(state)

    assert state["position"] == 0
    assert state["current_song"]["id"] == 1  # paused clock never rolls over


def test_clock_advances_regardless_of_listeners():
    """The playback clock is owned by the background loop and must advance with no
    listeners connected (issue #5) -- update_radio_position takes no listener input."""
    state = _state(current_song=_song(1, duration=180), is_playing=True,
                   position=0, last_update=time.time() - 7)

    backend_api.update_radio_position(state)

    assert state["position"] >= 7
    assert state["is_playing"] is True  # not paused just because nobody is listening


@pytest.mark.asyncio
async def test_auto_populate_fills_queue_when_low(monkeypatch):
    class FakeAgent:
        async def search_songs(self, message, limit=10):
            return {"response": "ok", "songs": [_song(10), _song(11), _song(12)]}

    async def fake_get_agent():
        return FakeAgent()

    monkeypatch.setattr(backend_api, "get_agent", fake_get_agent)

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

    monkeypatch.setattr(backend_api, "get_agent", fake_get_agent)

    state = _state(queue=[_song(i) for i in range(6)])
    await backend_api.auto_populate_queue(state)

    assert called is False
    assert len(state["queue"]) == 6
