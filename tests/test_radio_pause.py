"""Pausing the radio stops the broadcast itself (RAD-07).

A pause used to flip ``is_playing`` while Liquidsoap kept decoding and encoding,
so the page read PAUSED over a stream that was still playing and nothing was
saved. Now Pause/Resume stop and start the stream's Icecast output, a stream that
can't be reached makes them fail visibly (RAD-09), and the background loop holds
the stream to the stored wish so a pause survives a Liquidsoap restart (RAD-04).

No real stream: the harbor call and the radio store are faked.
"""
import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service
from src.api.dependencies import get_radio_store
from src.api.radio_service import reconcile_with_stream, stream_running_mismatch
from src.api.routers import radio as radio_router

_SECRET = "test-secret-value"


class FakeStore:
    def __init__(self, state):
        self._state = state
        self.saved = False

    async def load_state(self):
        return self._state

    async def save_state(self, state):
        self._state = state
        self.saved = True


def _editor(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


def _song(song_id):
    return {"id": song_id, "title": f"Song {song_id}", "duration": 180}


def _on_air(song_id, running):
    return {
        "filename": f"/audio_library/{song_id}_song.mp3",
        "source": "queue",
        "elapsed": 10.0,
        "remaining": 170.0,
        "running": running,
    }


@pytest.fixture
def client():
    yield TestClient(backend_api.app)
    backend_api.app.dependency_overrides.clear()


def _calls(monkeypatch, answer=True):
    """Record the start/stop calls the endpoints make; the stream answers ``answer``."""
    calls = []

    async def fake(running):
        calls.append(running)
        return answer

    monkeypatch.setattr(radio_router, "set_stream_running", fake)
    return calls


def test_pause_stops_the_stream_and_records_the_pause(monkeypatch, client):
    calls = _calls(monkeypatch)
    store = FakeStore({"is_playing": True, "current_song": _song(1), "queue": []})
    backend_api.app.dependency_overrides[get_radio_store] = lambda: store

    resp = client.post("/api/radio/pause", headers=_editor(monkeypatch))

    assert resp.status_code == 200
    assert calls == [False]
    assert store._state["is_playing"] is False


def test_resume_starts_the_stream(monkeypatch, client):
    calls = _calls(monkeypatch)
    store = FakeStore({"is_playing": False, "current_song": _song(1), "queue": []})
    backend_api.app.dependency_overrides[get_radio_store] = lambda: store

    resp = client.post("/api/radio/play", headers=_editor(monkeypatch))

    assert resp.status_code == 200
    assert calls == [True]
    assert store._state["is_playing"] is True


def test_a_pause_the_stream_did_not_take_says_so_and_changes_nothing(monkeypatch, client):
    _calls(monkeypatch, answer=False)
    store = FakeStore({"is_playing": True, "current_song": _song(1), "queue": []})
    backend_api.app.dependency_overrides[get_radio_store] = lambda: store

    resp = client.post("/api/radio/pause", headers=_editor(monkeypatch))

    assert resp.status_code == 503
    assert store._state["is_playing"] is True
    assert store.saved is False


def _listener(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "listener"}


def test_a_listener_cannot_pause_the_radio(monkeypatch, client):
    """Stopping takes the radio away from everyone else, so it stays editor+."""
    calls = _calls(monkeypatch)

    resp = client.post("/api/radio/pause", headers=_listener(monkeypatch))

    assert resp.status_code == 403
    assert calls == []


def test_a_listener_can_start_a_paused_radio(monkeypatch, client):
    """Starting is what tuning in to a paused radio needs (RAD-03, ACCT-15)."""
    calls = _calls(monkeypatch)
    store = FakeStore({"is_playing": False, "current_song": _song(1), "queue": []})
    backend_api.app.dependency_overrides[get_radio_store] = lambda: store

    resp = client.post("/api/radio/play", headers=_listener(monkeypatch))

    assert resp.status_code == 200
    assert calls == [True]
    assert store._state["is_playing"] is True


def test_starting_the_radio_still_needs_a_signed_in_user(monkeypatch, client):
    calls = _calls(monkeypatch)
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)

    resp = client.post("/api/radio/play")

    assert resp.status_code in (401, 403)
    assert calls == []


@pytest.mark.parametrize(
    "is_playing, running, mismatch",
    [
        (False, True, True),    # paused, but Liquidsoap restarted broadcasting
        (True, False, True),    # playing, but the output is stopped
        (True, True, False),
        (False, False, False),
    ],
)
def test_the_stream_is_held_to_the_stored_wish(is_playing, running, mismatch):
    assert stream_running_mismatch({"is_playing": is_playing}, {"running": running}) is mismatch


def test_a_stream_that_does_not_report_running_is_left_alone():
    assert stream_running_mismatch({"is_playing": False}, {"filename": "x"}) is False


def test_a_stopped_stream_does_not_resume_an_idle_paused_radio():
    """A stopped output still reports the track it stopped on. With no current song
    stored, that must not read as audio coming on air and undo the pause."""
    state = {"current_song": None, "queue": [], "is_playing": False, "position": 0}

    reconcile_with_stream(state, _on_air(1, running=False), _song(1), "queue")

    assert state["is_playing"] is False


def test_a_running_stream_still_starts_an_idle_broadcast():
    state = {"current_song": None, "queue": [], "is_playing": False, "position": 0}

    reconcile_with_stream(state, _on_air(1, running=True), _song(1), "queue")

    assert state["is_playing"] is True
