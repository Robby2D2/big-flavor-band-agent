"""Tests for the /produce versions management endpoints (issue #43).

Exercise set-default / rename / delete and the versions list enrichment against
a fake DatabaseManager and a tmp audio library, with no live DB, LLM, or real
audio decode. The router is editor-gated, so calls carry the service secret.

Covered contracts:
  - the versions list returns a display name (producer name or label default),
    file size, and the steps/intensity/duration captured in metrics,
  - set-default publishes exactly one version and refreshes the radio override,
  - rename persists a display name (and rejects empty),
  - delete removes the row and its file, refuses the song's last version, and
    when the deleted version was the default promotes a fallback (preferring the
    original) and refreshes the radio override.
"""
import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service
from src.api.dependencies import get_db


_SECRET = "test-secret-value"


def _editor_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


class FakeDB:
    """In-memory stand-in for the song_versions persistence the router uses."""

    def __init__(self):
        self._versions = {}
        self._next_id = 1

    def insert(self, song_id, audio_path, label, published, name=None, metrics=None):
        vid = self._next_id
        self._next_id += 1
        # created_at ordering: later inserts are newer.
        row = {
            "id": vid,
            "song_id": song_id,
            "audio_path": audio_path,
            "label": label,
            "name": name,
            "is_published": published,
            "metrics": metrics,
            "created_at": datetime.datetime(2026, 1, 1) + datetime.timedelta(minutes=vid),
        }
        self._versions[vid] = row
        return row

    async def ensure_original_version(self, song_id, audio_path):
        for v in self._versions.values():
            if v["song_id"] == song_id and v["label"] == "original":
                return v
        return self.insert(song_id, audio_path, "original", True)

    async def list_song_versions(self, song_id):
        rows = [v for v in self._versions.values() if v["song_id"] == song_id]
        return sorted(rows, key=lambda v: v["created_at"], reverse=True)

    async def get_song_version(self, version_id):
        return self._versions.get(version_id)

    async def publish_song_version(self, song_id, version_id):
        if version_id not in self._versions:
            return None
        for v in self._versions.values():
            if v["song_id"] == song_id:
                v["is_published"] = False
        self._versions[version_id]["is_published"] = True
        return self._versions[version_id]

    async def rename_song_version(self, version_id, name):
        row = self._versions.get(version_id)
        if row is None:
            return None
        row["name"] = name
        return row

    async def count_song_versions(self, song_id):
        return len([v for v in self._versions.values() if v["song_id"] == song_id])

    async def pick_fallback_version(self, song_id, exclude_version_id):
        candidates = [
            v
            for v in self._versions.values()
            if v["song_id"] == song_id and v["id"] != exclude_version_id
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda v: (v["label"] == "original", v["created_at"]), reverse=True
        )
        return candidates[0]

    async def delete_song_version(self, version_id):
        return self._versions.pop(version_id, None)


@pytest.fixture
def versions_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    (audio_library / "5_test-track.mp3").write_bytes(b"original-audio")
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    radio_service.set_published_version_paths({})

    db = FakeDB()
    backend_api.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(backend_api.app), db, audio_library
    finally:
        backend_api.app.dependency_overrides.clear()
        radio_service.set_published_version_paths({})


def test_versions_endpoints_require_service_secret(versions_client):
    client, *_ = versions_client
    assert client.get("/api/produce/songs/5/versions").status_code == 401
    assert client.post("/api/produce/versions/1/default").status_code == 401
    assert client.patch("/api/produce/versions/1", json={"name": "x"}).status_code == 401
    assert client.delete("/api/produce/versions/1").status_code == 401


def test_list_versions_enriches_name_size_and_metrics(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    original = audio_library / "5_test-track.mp3"
    db.insert(5, str(original), "original", True)
    cleaned_file = audio_library / "produced" / "5_cleaned_1.wav"
    cleaned_file.parent.mkdir(parents=True, exist_ok=True)
    cleaned_file.write_bytes(b"cleaned-audio")
    db.insert(
        5,
        str(cleaned_file),
        "cleaned",
        False,
        name="Punchy master",
        metrics={
            "after": {"duration_seconds": 31.5},
            "steps_applied": [{"step": "noise_reduction"}, {"step": "mastering"}],
            "aggressiveness": "aggressive",
        },
    )

    resp = client.get("/api/produce/songs/5/versions", headers=_editor_headers(monkeypatch))
    assert resp.status_code == 200, resp.text
    versions = {v["name"]: v for v in resp.json()["versions"]}

    # Original with no name falls back to a label-derived display name.
    assert "Original" in versions
    assert versions["Original"]["label"] == "original"
    assert versions["Original"]["is_published"] is True
    assert versions["Original"]["file_size_bytes"] == len(b"original-audio")

    # Cleaned version surfaces producer name + steps/intensity/duration + size.
    cleaned = versions["Punchy master"]
    assert cleaned["aggressiveness"] == "aggressive"
    assert cleaned["duration_seconds"] == 31.5
    assert [s["step"] for s in cleaned["steps_applied"]] == ["noise_reduction", "mastering"]
    assert cleaned["file_size_bytes"] == len(b"cleaned-audio")


def test_set_default_publishes_one_and_refreshes_override(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    original = db.insert(5, str(audio_library / "5_test-track.mp3"), "original", True)
    cleaned_path = audio_library / "produced" / "5_cleaned_1.wav"
    cleaned = db.insert(5, str(cleaned_path), "cleaned", False)

    resp = client.post(
        f"/api/produce/versions/{cleaned['id']}/default",
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_published"] is True

    published = [v for v in db._versions.values() if v["is_published"]]
    assert len(published) == 1
    assert published[0]["id"] == cleaned["id"]
    assert original["is_published"] is False
    assert radio_service._published_version_paths[5] == str(cleaned_path)


def test_set_default_unknown_version_404(versions_client, monkeypatch):
    client, *_ = versions_client
    resp = client.post(
        "/api/produce/versions/999/default", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 404


def test_rename_persists_name(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    v = db.insert(5, str(audio_library / "5_test-track.mp3"), "original", True)
    resp = client.patch(
        f"/api/produce/versions/{v['id']}",
        json={"name": "  Radio cut  "},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Radio cut"
    assert db._versions[v["id"]]["name"] == "Radio cut"


def test_rename_rejects_empty(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    v = db.insert(5, str(audio_library / "5_test-track.mp3"), "original", True)
    resp = client.patch(
        f"/api/produce/versions/{v['id']}",
        json={"name": "   "},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 400


def test_delete_refuses_last_version(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    v = db.insert(5, str(audio_library / "5_test-track.mp3"), "original", True)
    resp = client.delete(
        f"/api/produce/versions/{v['id']}", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 409
    assert v["id"] in db._versions


def test_delete_default_promotes_original_fallback(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    original_path = audio_library / "5_test-track.mp3"
    original = db.insert(5, str(original_path), "original", False)
    cleaned_path = audio_library / "produced" / "5_cleaned_1.wav"
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_bytes(b"cleaned-audio")
    cleaned = db.insert(5, str(cleaned_path), "cleaned", True)
    radio_service.set_published_version_path(5, str(cleaned_path))

    resp = client.delete(
        f"/api/produce/versions/{cleaned['id']}", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_default_version_id"] == original["id"]

    # Deleted row and its file are gone; original is now the published default.
    assert cleaned["id"] not in db._versions
    assert not cleaned_path.exists()
    assert db._versions[original["id"]]["is_published"] is True
    assert radio_service._published_version_paths[5] == str(original_path)


def test_delete_non_default_keeps_default(versions_client, monkeypatch):
    client, db, audio_library = versions_client
    db.insert(5, str(audio_library / "5_test-track.mp3"), "original", True)
    cleaned_path = audio_library / "produced" / "5_cleaned_1.wav"
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned_path.write_bytes(b"cleaned-audio")
    cleaned = db.insert(5, str(cleaned_path), "cleaned", False)

    resp = client.delete(
        f"/api/produce/versions/{cleaned['id']}", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_default_version_id"] is None
    assert cleaned["id"] not in db._versions
    assert not cleaned_path.exists()
