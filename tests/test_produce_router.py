"""Tests for the production UI router (issue #28).

The /api/produce/* endpoints are a thin, path-safe wrapper over the existing MCP
audio-cleanup tools: the browser sends a catalog song_id only, and the backend
resolves the source audio path and a NON-destructive output path before calling
the tool. These guards assert that contract without touching a live DB, LLM, or
real audio:
  - the endpoints are editor-gated (reject calls without the service secret),
  - analyze/auto-clean route to the right MCP tool for the resolved source file,
  - the auto-clean output path is derived non-destructively (never the source,
    always under the produced/ subdir),
  - steps_override toggles are forwarded to the tool.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service
from src.api.routers import produce
from src.api.dependencies import get_agent, get_db


_SECRET = "test-secret-value"


def _editor_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


class FakeAgent:
    """Captures the tool calls the router makes."""

    def __init__(self):
        self.calls = []

    async def execute_tool(self, tool_name, parameters):
        self.calls.append((tool_name, parameters))
        return {"status": "success", "tool": tool_name, "echo": parameters}


class FakeDB:
    async def get_all_songs(self):
        return [
            {"id": 2, "title": "Song Two"},
            {"id": 1, "title": "Song One"},
        ]


@pytest.fixture
def produce_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    (audio_library / "5_test-track.mp3").write_bytes(b"audio")
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)

    agent = FakeAgent()
    backend_api.app.dependency_overrides[get_agent] = lambda: agent
    backend_api.app.dependency_overrides[get_db] = lambda: FakeDB()
    try:
        yield TestClient(backend_api.app), agent, audio_library
    finally:
        backend_api.app.dependency_overrides.clear()


def test_produce_endpoints_require_service_secret(produce_client):
    client, _, _ = produce_client
    # No service-secret header -> backend trust boundary rejects with 401.
    assert client.get("/api/produce/songs").status_code == 401
    assert client.post("/api/produce/analyze", json={"song_id": 5}).status_code == 401
    assert client.post("/api/produce/auto-clean", json={"song_id": 5}).status_code == 401


def test_list_catalog_songs_returns_id_title(produce_client, monkeypatch):
    client, _, _ = produce_client
    resp = client.get("/api/produce/songs", headers=_editor_headers(monkeypatch))
    assert resp.status_code == 200
    assert resp.json() == {
        "songs": [{"id": 2, "title": "Song Two"}, {"id": 1, "title": "Song One"}]
    }


def test_analyze_routes_to_tool_with_resolved_source(produce_client, monkeypatch):
    client, agent, audio_library = produce_client
    resp = client.post(
        "/api/produce/analyze",
        json={"song_id": 5},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200
    tool_name, params = agent.calls[0]
    assert tool_name == "analyze_and_recommend_processing"
    assert params["file_path"] == str(audio_library / "5_test-track.mp3")


def test_auto_clean_output_is_non_destructive(produce_client, monkeypatch):
    client, agent, audio_library = produce_client
    resp = client.post(
        "/api/produce/auto-clean",
        json={
            "song_id": 5,
            "aggressiveness": "aggressive",
            "steps_override": {"eq": False, "master": True},
        },
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200

    tool_name, params = agent.calls[0]
    assert tool_name == "auto_clean_recording"

    source = str(audio_library / "5_test-track.mp3")
    assert params["file_path"] == source
    # Output must never overwrite the catalog source, and must land under produced/.
    output = Path(params["output_path"])
    assert str(output) != source
    assert output.parent == audio_library / produce.PRODUCED_SUBDIR
    assert params["aggressiveness"] == "aggressive"
    assert params["steps_override"] == {"eq": False, "master": True}


def test_auto_clean_unknown_song_returns_404(produce_client, monkeypatch):
    client, _, _ = produce_client
    resp = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 9999},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 404
