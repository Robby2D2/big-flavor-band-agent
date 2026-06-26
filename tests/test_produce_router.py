"""Tests for the produce / audio-cleanup router (issues #28, #30).

The /api/produce/* endpoints are a path-safe wrapper over the existing MCP
audio-cleanup tools: the browser sends a catalog song_id only, and the backend
resolves the source audio path and a NON-destructive output path before calling
the tool. These guards assert the contract without a live DB, LLM, or real audio:
  - endpoints are editor-gated (reject calls without the service secret),
  - analyze/auto-clean route to the right MCP tool for the resolved source file,
    and steps_override toggles are forwarded to the tool (issue #28),
  - the output path is derived non-destructively (never the source, always under
    the produced/ subdir),
  - clean() returns a candidate under produced/ plus a before/after metrics diff
    (LUFS/peak/duration + steps + noise reduction) (issue #30),
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
    """Captures the tool calls the router makes and stands in for the MCP agent.

    Writes the 'cleaned' output file when an output_path is supplied (clean /
    auto-clean), and returns a cleanup-style payload. The analyze call passes no
    output_path, so the write is conditional.
    """

    def __init__(self):
        self.calls = []

    async def execute_tool(self, tool_name, parameters):
        self.calls.append((tool_name, parameters))
        if "output_path" in parameters:
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

    async def find_cleaned_version_by_dedup_key(self, song_id, dedup_key):
        for v in self._versions.values():
            if (
                v["song_id"] == song_id
                and v["label"] == "cleaned"
                and (v["metrics"] or {}).get("dedup_key") == dedup_key
            ):
                return v
        return None

    async def replace_song_version_audio(self, version_id, audio_path, metrics=None):
        row = self._versions.get(version_id)
        if row is None:
            return None
        row["audio_path"] = audio_path
        row["metrics"] = metrics
        return row

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
    # No service-secret header -> backend trust boundary rejects with 401.
    assert client.get("/api/produce/songs").status_code == 401
    assert client.post("/api/produce/analyze", json={"song_id": 5}).status_code == 401
    assert client.post("/api/produce/auto-clean", json={"song_id": 5}).status_code == 401
    assert client.post("/api/produce/clean", json={"song_id": 5}).status_code == 401
    assert (
        client.post(
            "/api/produce/approve", json={"song_id": 5, "candidate_path": "x"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/produce/discard", json={"candidate_path": "x"}
        ).status_code
        == 401
    )


def test_list_catalog_songs_returns_id_title(produce_client, monkeypatch):
    client, *_ = produce_client
    resp = client.get("/api/produce/songs", headers=_editor_headers(monkeypatch))
    assert resp.status_code == 200
    assert resp.json() == {"songs": [{"id": 5, "title": "Test Track"}]}


def test_analyze_routes_to_tool_with_resolved_source(produce_client, monkeypatch):
    client, agent, _, _, audio_library = produce_client
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
    client, agent, _, _, audio_library = produce_client
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
    client, *_ = produce_client
    resp = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 9999},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 404


def test_auto_clean_creates_unpublished_candidate_version(produce_client, monkeypatch):
    """A successful auto-clean saves a candidate version without changing the default."""
    client, _, _, db, _ = produce_client
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"duration_seconds": 12.0})

    # Seed an existing published original so we can assert the default is unchanged.
    original = db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)

    resp = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"]["status"] == "success"
    assert body["version"]["is_published"] is False

    # A new cleaned candidate exists, unpublished, carrying step/intensity/produced-at.
    cleaned = [v for v in db._versions.values() if v["label"] == "cleaned"]
    assert len(cleaned) == 1
    version = cleaned[0]
    assert version["is_published"] is False
    assert version["metrics"]["aggressiveness"] == "moderate"
    assert [s["step"] for s in version["metrics"]["steps_applied"]] == [
        "noise_reduction",
        "mastering",
    ]
    assert "produced_at" in version["metrics"]

    # The original is still the published default — the candidate did not promote.
    assert original["is_published"] is True


def test_auto_clean_identical_rerun_replaces_candidate(produce_client, monkeypatch):
    """Re-running auto-clean with the same steps/intensity replaces, not duplicates."""
    client, _, _, db, _ = produce_client
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"duration_seconds": 12.0})
    db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)

    first = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    second = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    assert first.status_code == 200
    assert second.status_code == 200

    cleaned = [v for v in db._versions.values() if v["label"] == "cleaned"]
    assert len(cleaned) == 1, "identical re-run should replace, not append"
    # Same version row id reused across the two runs.
    assert first.json()["version"]["version_id"] == second.json()["version"]["version_id"]


def test_auto_clean_different_intensity_adds_distinct_candidate(produce_client, monkeypatch):
    """Different intensity is a distinct candidate, not a replacement."""
    client, _, _, db, _ = produce_client
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"duration_seconds": 12.0})
    db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)

    client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "aggressive"},
        headers=_editor_headers(monkeypatch),
    )

    cleaned = [v for v in db._versions.values() if v["label"] == "cleaned"]
    assert len(cleaned) == 2
    intensities = {v["metrics"]["aggressiveness"] for v in cleaned}
    assert intensities == {"moderate", "aggressive"}


def test_auto_clean_failure_creates_no_version(produce_client, monkeypatch):
    """A failed auto-clean leaves the versions list and default untouched."""
    client, agent, _, db, _ = produce_client
    db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)

    async def failing_tool(tool_name, parameters):
        agent.calls.append((tool_name, parameters))
        return {"status": "error", "error": "decode failed"}

    monkeypatch.setattr(agent, "execute_tool", failing_tool)

    resp = client.post(
        "/api/produce/auto-clean",
        json={"song_id": 5, "aggressiveness": "moderate"},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["result"]["status"] == "error"
    assert "version" not in body

    # No cleaned candidate was created; only the seeded original remains.
    assert [v["label"] for v in db._versions.values()] == ["original"]


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
    original = db._insert(5, "/app/audio_library/5_test-track.mp3", "original", True)
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
    assert original["is_published"] is False

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
