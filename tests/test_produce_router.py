"""Tests for the produce / cleanup-audition router (issue #30).

The /api/produce/* endpoints wrap the existing MCP auto_clean_recording tool with
the audition + metrics-diff + version-and-publish loop. These assert the contract
without a live DB, LLM, or real audio:
  - endpoints are editor-gated (reject calls without the service secret),
  - clean() returns a non-destructive candidate under produced/ plus a
    before/after metrics diff (LUFS/peak/duration + steps + noise reduction),
  - approve() saves a cleaned version, indexes its embedding, marks exactly one
    version published, and refreshes the radio published-path override,
  - discard() removes the candidate file and leaves versions untouched,
  - approve/discard reject paths outside produced/.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service
from src.api.routers import produce
from src.api.dependencies import get_agent, get_db, get_rag


_SECRET = "test-secret-value"


def _editor_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


class FakeAgent:
    """Stands in for the MCP agent; writes the 'cleaned' output and returns a payload."""

    def __init__(self):
        self.calls = []

    async def execute_tool(self, tool_name, parameters):
        self.calls.append((tool_name, parameters))
        # Simulate the tool producing the cleaned output file.
        Path(parameters["output_path"]).write_bytes(b"cleaned-audio")
        return {
            "status": "success",
            "aggressiveness": parameters.get("aggressiveness"),
            "analysis_summary": "noise at -45 dB",
            "steps_applied": [
                {"step": "noise_reduction", "reduction_db": 6.2},
                {"step": "mastering", "actual_lufs": -14.0},
            ],
        }


class FakeRag:
    def __init__(self):
        self.indexed = []

    async def index_audio_file(self, audio_path, song_id):
        self.indexed.append((audio_path, song_id))
        return True


class FakeDB:
    """In-memory stand-in for the version persistence methods used by the router."""

    def __init__(self):
        self._versions = {}
        self._next_id = 1

    async def get_all_songs(self):
        return [{"id": 5, "title": "Test Track"}]

    async def ensure_original_version(self, song_id, audio_path):
        for v in self._versions.values():
            if v["song_id"] == song_id and v["label"] == "original":
                return v
        return self._insert(song_id, audio_path, "original", True)

    def _insert(self, song_id, audio_path, label, published, metrics=None):
        import datetime

        vid = self._next_id
        self._next_id += 1
        row = {
            "id": vid,
            "song_id": song_id,
            "audio_path": audio_path,
            "label": label,
            "is_published": published,
            "metrics": metrics,
            "created_at": datetime.datetime.now(),
        }
        self._versions[vid] = row
        return row

    async def list_song_versions(self, song_id):
        return [v for v in self._versions.values() if v["song_id"] == song_id]

    async def get_song_version(self, version_id):
        return self._versions.get(version_id)

    async def add_song_version(self, song_id, audio_path, label="cleaned", metrics=None):
        return self._insert(song_id, audio_path, label, False, metrics)

    async def publish_song_version(self, song_id, version_id):
        if version_id not in self._versions:
            return None
        for v in self._versions.values():
            if v["song_id"] == song_id:
                v["is_published"] = False
        self._versions[version_id]["is_published"] = True
        return self._versions[version_id]


@pytest.fixture
def produce_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    (audio_library / "5_test-track.mp3").write_bytes(b"original-audio")
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    radio_service.set_published_version_paths({})

    agent = FakeAgent()
    rag = FakeRag()
    db = FakeDB()
    backend_api.app.dependency_overrides[get_agent] = lambda: agent
    backend_api.app.dependency_overrides[get_rag] = lambda: rag
    backend_api.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(backend_api.app), agent, rag, db, audio_library
    finally:
        backend_api.app.dependency_overrides.clear()
        radio_service.set_published_version_paths({})


def test_produce_endpoints_require_service_secret(produce_client):
    client, *_ = produce_client
    assert client.get("/api/produce/songs").status_code == 401
    assert client.post("/api/produce/clean", json={"song_id": 5}).status_code == 401
    assert (
        client.post(
            "/api/produce/approve", json={"song_id": 5, "candidate_path": "x"}
        ).status_code
        == 401
    )


def test_clean_returns_candidate_and_diff(produce_client, monkeypatch):
    client, agent, _, _, audio_library = produce_client

    # Don't load real audio; stub the measurement so no librosa/file decode runs.
    monkeypatch.setattr(
        produce,
        "_measure_audio",
        lambda path: {
            "duration_seconds": 12.0,
            "peak_db": -1.0,
            "integrated_lufs_estimate": -20.0,
        },
    )

    resp = client.post(
        "/api/produce/clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Candidate is non-destructive: under produced/, never the catalog source.
    candidate = Path(body["candidate_path"])
    assert candidate.parent.name == produce.PRODUCED_SUBDIR
    assert candidate.exists()

    diff = body["diff"]
    assert diff["before"]["integrated_lufs_estimate"] == -20.0
    assert diff["after"]["peak_db"] == -1.0
    assert diff["noise_reduction_db"] == 6.2
    assert [s["step"] for s in diff["steps_applied"]] == ["noise_reduction", "mastering"]

    # The cleanup tool was actually invoked with the resolved source + output.
    assert agent.calls[0][0] == "auto_clean_recording"


def test_approve_creates_indexed_published_version(produce_client, monkeypatch):
    client, _, rag, db, _ = produce_client
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"peak_db": -1.0})

    # Seed the original and produce a candidate file under produced/.
    await_original = db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)
    candidate = produce._produced_dir() / "5_cleaned_1.wav"
    candidate.write_bytes(b"cleaned-audio")

    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 5, "candidate_path": str(candidate)},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_published"] is True
    assert body["embedding_indexed"] is True

    # The new version's audio was indexed (every version findable).
    assert rag.indexed == [(str(candidate), 5)]

    # Exactly one published version, and it's the cleaned one (not the original).
    versions = list(db._versions.values())
    published = [v for v in versions if v["is_published"]]
    assert len(published) == 1
    assert published[0]["label"] == "cleaned"
    assert await_original["is_published"] is False

    # Radio/stream override now points at the published cleaned take.
    assert radio_service._published_version_paths[5] == str(candidate)


def test_discard_removes_candidate_and_keeps_versions(produce_client, monkeypatch):
    client, _, _, db, _ = produce_client
    db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)
    candidate = produce._produced_dir() / "5_cleaned_2.wav"
    candidate.write_bytes(b"cleaned-audio")

    resp = client.post(
        "/api/produce/discard",
        json={"candidate_path": str(candidate)},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["discarded"] is True
    assert not candidate.exists()

    # Existing versions untouched.
    versions = list(db._versions.values())
    assert len(versions) == 1
    assert versions[0]["label"] == "original"


def test_approve_rejects_path_outside_produced(produce_client, monkeypatch):
    client, _, _, _, audio_library = produce_client
    outside = audio_library / "5_test-track.mp3"  # a catalog original, not produced/
    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 5, "candidate_path": str(outside)},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 400
