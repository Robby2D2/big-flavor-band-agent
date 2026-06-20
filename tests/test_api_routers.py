"""Tests for the backend_api router split (issue #7).

These guard the structural refactor that decomposed the single ~890-line
`backend_api.py` into per-concern routers plus a `RadioService`. They assert
the externally observable contract is unchanged: every endpoint is still
mounted at the same path/method, the radio playlist builder still applies the
Liquidsoap path rewrite, and the audio-stream route still serves files with
HTTP Range support.

No live DB, no LLM, no real catalog — the audio dir is a temp dir pointed at
via the module-level AUDIO_LIBRARY_DIR constant, and the RadioService is
exercised directly.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api.radio_service import RadioService, _build_and_write_playlist, _find_audio_file


# --- Routes are all still mounted at the same path/method ------------------

EXPECTED_ROUTES = {
    ("GET", "/"),
    ("GET", "/health"),
    ("POST", "/api/users"),
    ("GET", "/api/users/{user_id}/role"),
    ("GET", "/api/admin/users"),
    ("PUT", "/api/admin/users/role"),
    ("POST", "/api/search/natural"),
    ("POST", "/api/search/text"),
    ("POST", "/api/search/lyrics"),
    ("GET", "/api/songs/{song_id}/lyrics"),
    ("POST", "/api/agent/chat"),
    ("POST", "/api/agent/dj/request"),
    ("POST", "/api/agent/dj/playlist"),
    ("GET", "/api/radio/state"),
    ("POST", "/api/radio/queue/add"),
    ("POST", "/api/radio/skip"),
    ("POST", "/api/radio/queue/remove"),
    ("POST", "/api/radio/play"),
    ("POST", "/api/radio/pause"),
    ("GET", "/stream"),
    ("GET", "/stream.m3u"),
    ("GET", "/api/audio/stream/{song_id}"),
    ("GET", "/api/tools/list"),
    ("POST", "/api/tools/execute"),
}


def test_all_expected_routes_are_mounted():
    spec = TestClient(backend_api.app).get("/openapi.json").json()
    mounted = {
        (method.upper(), path)
        for path, ops in spec["paths"].items()
        for method in ops
    }
    missing = EXPECTED_ROUTES - mounted
    assert not missing, f"routes missing after refactor: {sorted(missing)}"


def test_health_endpoints_unchanged():
    client = TestClient(backend_api.app)
    assert client.get("/").json() == {
        "status": "ok",
        "service": "BigFlavor Band Agent API",
        "version": "1.0.0",
    }
    assert client.get("/health").json() == {"status": "healthy"}


# --- Radio invariant: playlist path rewrite is preserved ------------------

def test_build_and_write_playlist_applies_liquidsoap_path_rewrite(tmp_path):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    (audio_library / "1_song-one.mp3").write_bytes(b"a")
    (audio_library / "2_song-two.mp3").write_bytes(b"b")
    playlist_file = tmp_path / "playlist" / "radio.m3u"

    _build_and_write_playlist(
        {"id": 1, "title": "Song One"},
        [{"id": 2, "title": "Song Two"}],
        audio_library,
        playlist_file,
    )

    lines = playlist_file.read_text().splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines.index("#EXTINF:-1,Song One") < lines.index("#EXTINF:-1,Song Two")
    rewritten = str(audio_library / "1_song-one.mp3").replace(
        "/app/audio_library", "/audio_library"
    )
    assert rewritten in lines


def test_build_and_write_playlist_skips_songs_without_audio(tmp_path):
    playlist_file = tmp_path / "radio.m3u"
    _build_and_write_playlist({"id": 99, "title": "Missing"}, [], tmp_path, playlist_file)
    assert playlist_file.read_text().splitlines() == ["#EXTM3U"]


# --- RadioService queue/playback logic ------------------------------------

def test_advance_to_next_song_promotes_queue_head(tmp_path, monkeypatch):
    svc = RadioService()
    # Avoid touching the real /app playlist path during the test.
    monkeypatch.setattr(svc, "write_playlist_file", lambda: None)
    svc.radio_state["queue"] = [
        {"id": 1, "title": "First"},
        {"id": 2, "title": "Second"},
    ]

    svc.advance_to_next_song()

    assert svc.radio_state["current_song"]["id"] == 1
    assert svc.radio_state["is_playing"] is True
    assert [s["id"] for s in svc.radio_state["queue"]] == [2]


def test_advance_with_empty_queue_stops_playback(monkeypatch):
    svc = RadioService()
    monkeypatch.setattr(svc, "write_playlist_file", lambda: None)
    svc.radio_state["current_song"] = {"id": 5, "title": "Last"}
    svc.radio_state["is_playing"] = True

    svc.advance_to_next_song()

    assert svc.radio_state["current_song"] is None
    assert svc.radio_state["is_playing"] is False


def test_remove_from_queue_drops_matching_song():
    client = TestClient(backend_api.app)
    from src.api.routers import radio as radio_router

    radio_router.radio_service.radio_state["queue"] = [
        {"id": 1, "title": "Keep"},
        {"id": 2, "title": "Drop"},
    ]
    resp = client.post("/api/radio/queue/remove", json={"song_id": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"removed": True, "queue_length": 1}
    assert [s["id"] for s in radio_router.radio_service.radio_state["queue"]] == [1]


# --- Audio streaming route (Range support), AUDIO_LIBRARY_DIR patchable ----

@pytest.fixture
def audio_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    payload = bytes(range(256)) * 8
    (audio_library / "5_test-track.mp3").write_bytes(payload)
    # The route resolves AUDIO_LIBRARY_DIR off the backend_api module at call
    # time, so monkeypatching it here must flow through to the handler.
    monkeypatch.setattr(backend_api, "AUDIO_LIBRARY_DIR", audio_library)
    return TestClient(backend_api.app), payload


def test_stream_audio_full_request_returns_200(audio_client):
    client, payload = audio_client
    resp = client.get("/api/audio/stream/5")
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == payload


def test_stream_audio_range_request_returns_206(audio_client):
    client, payload = audio_client
    resp = client.get("/api/audio/stream/5", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == f"bytes 0-99/{len(payload)}"
    assert resp.content == payload[0:100]


def test_stream_audio_missing_song_returns_404(audio_client):
    client, _ = audio_client
    resp = client.get("/api/audio/stream/9999")
    assert resp.status_code == 404


def test_find_audio_file_matches_song_id_prefix(tmp_path):
    (tmp_path / "7_track.mp3").write_bytes(b"x")
    assert _find_audio_file(7, tmp_path).name == "7_track.mp3"
    assert _find_audio_file(8, tmp_path) is None
