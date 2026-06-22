"""Status-code contract tests for the single-track approve endpoint (issue #38).

Regression guard: approving a candidate whose audio file is missing must return
HTTP **404** (not 400) with detail "Candidate file not found", restoring the
pre-refactor contract from issue #29 / PR #37 while the shared
``publish_candidate_version`` helper stays shared with the batch runner.

Drives the real ``produce.router`` through a FastAPI ``TestClient`` with fake
db/rag (no live DB, LLM, or real audio) and a temp ``produced/`` dir, asserting:
  - missing candidate file -> 404 "Candidate file not found",
  - a path-safety / bad-input ValueError -> 400,
  - a publish/write failure -> 500,
  - a successful approve of a present candidate -> 200.
"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.routers import produce
from src.api.dependencies import get_db, get_rag

SERVICE_SECRET = "test-secret"
AUTH_HEADERS = {"X-Service-Secret": SERVICE_SECRET, "X-User-Role": "editor"}


class FakeRag:
    async def index_audio_file(self, audio_path, song_id):
        return True


class FakeDB:
    """Minimal db for approve; publish_song_version returns None to force a 500."""

    def __init__(self, publish_returns_none=False):
        self._publish_returns_none = publish_returns_none

    async def add_song_version(self, song_id, audio_path, label="cleaned", metrics=None):
        return {"id": song_id * 10, "song_id": song_id, "label": label}

    async def publish_song_version(self, song_id, version_id):
        if self._publish_returns_none:
            return None
        return {"id": version_id, "song_id": song_id, "is_published": True}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient over just the produce router, with fakes and a temp library."""
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    from src.api import radio_service

    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    radio_service.set_published_version_paths({})
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"peak_db": -1.0})
    monkeypatch.setenv("BACKEND_API_SECRET", SERVICE_SECRET)

    app = FastAPI()
    app.include_router(produce.router)
    app.dependency_overrides[get_db] = lambda: FakeDB()
    app.dependency_overrides[get_rag] = lambda: FakeRag()

    test_client = TestClient(app)
    test_client._app = app  # let tests swap the db override
    test_client._audio_library = audio_library
    return test_client


def _produced_candidate(audio_library, song_id=1, contents=b"cleaned"):
    produced = audio_library / produce.PRODUCED_SUBDIR
    produced.mkdir(parents=True, exist_ok=True)
    candidate = produced / f"{song_id}_cleaned_123.wav"
    if contents is not None:
        candidate.write_bytes(contents)
    return candidate


def test_missing_candidate_file_returns_404(client):
    # A path under produced/ that does not exist on disk.
    candidate = _produced_candidate(client._audio_library, contents=None)

    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 1, "candidate_path": str(candidate)},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Candidate file not found"


def test_path_outside_produced_returns_400(client):
    # A path that is not under produced/ — a bad request, not a missing resource.
    outside = client._audio_library / "1_track.mp3"
    outside.write_bytes(b"original")

    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 1, "candidate_path": str(outside)},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Candidate must be a produced file"


def test_publish_failure_returns_500(client):
    candidate = _produced_candidate(client._audio_library)
    client._app.dependency_overrides[get_db] = lambda: FakeDB(publish_returns_none=True)

    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 1, "candidate_path": str(candidate)},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to publish version"


def test_successful_approve_returns_200(client):
    candidate = _produced_candidate(client._audio_library)

    resp = client.post(
        "/api/produce/approve",
        json={"song_id": 1, "candidate_path": str(candidate)},
        headers=AUTH_HEADERS,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["song_id"] == 1
    assert body["is_published"] is True
