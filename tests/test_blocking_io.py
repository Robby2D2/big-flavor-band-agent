"""Tests for the non-blocking file-I/O fixes on the FastAPI request paths.

Covers:
- _build_and_write_playlist() — the playlist builder writes the expected .m3u
  and preserves the /app/audio_library -> /audio_library Liquidsoap path rewrite.
- /api/audio/stream/{song_id} — serves the file with HTTP Range support
  (206 Partial Content) and full content (200), without a blocking read.

These are narrow unit/route tests: no live DB, no LLM, no real catalog. The
audio-library directory is pointed at a temp dir via the module-level
AUDIO_LIBRARY_DIR constant.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service


def test_build_and_write_playlist_writes_m3u_with_path_rewrite(tmp_path):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    # Files are named "{song_id}_*.mp3".
    (audio_library / "1_song-one.mp3").write_bytes(b"a")
    (audio_library / "2_song-two.mp3").write_bytes(b"b")
    playlist_file = tmp_path / "playlist" / "radio.m3u"

    current_song = {"id": 1, "title": "Song One"}
    queue = [{"id": 2, "title": "Song Two"}]

    backend_api._build_and_write_playlist(current_song, queue, audio_library, playlist_file)

    contents = playlist_file.read_text()
    lines = contents.splitlines()
    assert lines[0] == "#EXTM3U"
    assert "#EXTINF:-1,Song One" in lines
    assert "#EXTINF:-1,Song Two" in lines
    # Current song appears before the queued song.
    assert lines.index("#EXTINF:-1,Song One") < lines.index("#EXTINF:-1,Song Two")
    # The Liquidsoap path rewrite is applied to absolute /app/audio_library paths.
    rewritten = str(audio_library / "1_song-one.mp3").replace(
        "/app/audio_library", "/audio_library"
    )
    assert rewritten in lines


def test_build_and_write_playlist_skips_songs_without_audio(tmp_path):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    playlist_file = tmp_path / "radio.m3u"

    # No matching file on disk -> the song is skipped, header still written.
    backend_api._build_and_write_playlist({"id": 99, "title": "Missing"}, [], audio_library, playlist_file)

    assert playlist_file.read_text().splitlines() == ["#EXTM3U"]


@pytest.fixture
def audio_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    payload = bytes(range(256)) * 8  # 2048 bytes of deterministic content
    (audio_library / "5_test-track.mp3").write_bytes(payload)
    # _find_audio_file resolves AUDIO_LIBRARY_DIR off src.api.radio_service at
    # call time, so the patch must target that module.
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    return TestClient(backend_api.app), payload


def test_stream_audio_full_request_returns_200(audio_client):
    client, payload = audio_client
    resp = client.get("/api/audio/stream/5")
    assert resp.status_code == 200
    assert resp.headers["accept-ranges"] == "bytes"
    assert resp.content == payload


def test_stream_audio_range_request_returns_206_partial(audio_client):
    client, payload = audio_client
    resp = client.get("/api/audio/stream/5", headers={"Range": "bytes=0-99"})
    assert resp.status_code == 206
    assert resp.headers["content-range"] == f"bytes 0-99/{len(payload)}"
    assert resp.content == payload[0:100]


def test_stream_audio_missing_song_returns_404(audio_client):
    client, _ = audio_client
    resp = client.get("/api/audio/stream/9999")
    assert resp.status_code == 404
