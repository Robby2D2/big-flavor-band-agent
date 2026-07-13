"""Tests for Demucs stem separation (issue #67).

Covers the two pieces that carry real logic without invoking Demucs, a live DB,
or an LLM:

- ``remix_stems`` — the stem downmix that folds a stem set (with per-stem
  gain/mute) back into a single candidate: correct duration, gain/mute honoured,
  and — critically — the input stem/original files are byte-for-byte unchanged
  (non-destructive), verified by checksum.
- The ``/api/produce/stems/*`` router endpoints — editor-gated; a separation job
  creates a queued stem set and kicks off the (monkeypatched) separator; the
  stems list surfaces job status; a stem streams; and a remix render produces a
  produced/ candidate that plugs into the existing approve flow. A separator
  failure is recorded as ``failed`` status.
"""
import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import backend_api
from src.api import radio_service
from src.api import stem_jobs
from src.api.routers import produce
from src.production import stem_separation
from src.api.dependencies import get_db


_SECRET = "test-secret-value"


def _editor_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_tone(path: Path, freq: float, seconds: float = 0.25, sr: int = 8000):
    """Write a short stereo sine tone WAV (a cheap stand-in for a real stem)."""
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    mono = 0.3 * np.sin(2 * np.pi * freq * t)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    sf.write(str(path), stereo, sr)


# ---- remix_stems: the pure downmix logic ----

def test_remix_duration_matches_source_and_inputs_unchanged(tmp_path):
    """A remix has the same duration as its stems and never mutates the inputs."""
    vocals = tmp_path / "vocals.wav"
    drums = tmp_path / "drums.wav"
    _write_tone(vocals, 220.0, seconds=0.25)
    _write_tone(drums, 440.0, seconds=0.25)
    before = {vocals: _sha(vocals), drums: _sha(drums)}

    out = tmp_path / "remix.wav"
    stem_separation.remix_stems(
        [{"name": "vocals", "path": str(vocals)}, {"name": "drums", "path": str(drums)}],
        str(out),
    )

    src_info = sf.info(str(vocals))
    out_info = sf.info(str(out))
    assert out_info.frames == src_info.frames
    assert out_info.samplerate == src_info.samplerate

    # Non-destructive: every input stem is byte-for-byte identical afterwards.
    for path, digest in before.items():
        assert _sha(path) == digest


def test_remix_mute_and_gain_are_honoured(tmp_path):
    """Muting a stem drops it; unity gain on the other reproduces it exactly."""
    vocals = tmp_path / "vocals.wav"
    drums = tmp_path / "drums.wav"
    _write_tone(vocals, 220.0, seconds=0.25)
    _write_tone(drums, 440.0, seconds=0.25)

    out = tmp_path / "remix.wav"
    stem_separation.remix_stems(
        [{"name": "vocals", "path": str(vocals)}, {"name": "drums", "path": str(drums)}],
        str(out),
        adjustments={"drums": {"mute": True}},
    )

    remix, _ = sf.read(str(out), always_2d=True)
    vocals_data, _ = sf.read(str(vocals), always_2d=True)
    # With drums muted and vocals at unity gain, the remix is just the vocals.
    assert np.allclose(remix, vocals_data, atol=1e-4)


def test_remix_all_muted_raises(tmp_path):
    vocals = tmp_path / "vocals.wav"
    _write_tone(vocals, 220.0)
    with pytest.raises(ValueError):
        stem_separation.remix_stems(
            [{"name": "vocals", "path": str(vocals)}],
            str(tmp_path / "remix.wav"),
            adjustments={"vocals": {"mute": True}},
        )


# ---- router endpoints ----

class FakeDB:
    """In-memory stand-in for the stem-set/stem/version DB methods the router uses."""

    def __init__(self):
        self.stem_sets = {}
        self.stems = {}
        self._next_set = 1
        self._next_stem = 1
        # A published original so _resolve_clean_source_path(version) can resolve.
        self.versions = {}

    async def create_stem_set(self, song_id, model, source_version_id=None):
        import datetime

        sid = self._next_set
        self._next_set += 1
        row = {
            "id": sid,
            "song_id": song_id,
            "source_version_id": source_version_id,
            "model": model,
            "status": "queued",
            "error": None,
            "created_at": datetime.datetime.now(),
        }
        self.stem_sets[sid] = row
        return row

    async def set_stem_set_status(self, stem_set_id, status, error=None):
        row = self.stem_sets.get(stem_set_id)
        if row is None:
            return None
        row["status"] = status
        row["error"] = error
        return row

    async def get_stem_set(self, stem_set_id):
        return self.stem_sets.get(stem_set_id)

    async def list_stem_sets(self, song_id):
        return [s for s in self.stem_sets.values() if s["song_id"] == song_id]

    async def add_stem(self, stem_set_id, name, path):
        sid = self._next_stem
        self._next_stem += 1
        row = {"id": sid, "stem_set_id": stem_set_id, "name": name, "path": path}
        self.stems[sid] = row
        return row

    async def list_stems(self, stem_set_id):
        return [s for s in self.stems.values() if s["stem_set_id"] == stem_set_id]

    async def get_stem(self, stem_id):
        return self.stems.get(stem_id)

    async def get_song_version(self, version_id):
        return self.versions.get(version_id)


@pytest.fixture
def stem_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    (audio_library / "5_test-track.mp3").write_bytes(b"original-audio")
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)

    db = FakeDB()
    backend_api.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(backend_api.app), db, audio_library
    finally:
        backend_api.app.dependency_overrides.clear()


def test_stem_endpoints_require_service_secret(stem_client):
    client, *_ = stem_client
    assert client.post("/api/produce/stems/separate", json={"song_id": 5}).status_code == 401
    assert client.get("/api/produce/songs/5/stems").status_code == 401
    assert client.get("/api/produce/stems/1/audio").status_code == 401
    assert client.post("/api/produce/stems/1/render", json={}).status_code == 401


def test_separate_creates_queued_set_and_starts_job(stem_client, monkeypatch):
    client, db, audio_library = stem_client

    captured = {}

    def fake_start(stem_set_id, source_path, output_dir, model_name, db_arg):
        captured["args"] = (stem_set_id, source_path, output_dir, model_name)

    monkeypatch.setattr(stem_jobs.manager, "start", fake_start)

    resp = client.post(
        "/api/produce/stems/separate",
        json={"song_id": 5},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()["stem_set"]
    assert body["status"] == "queued"
    assert body["model"] == stem_separation.DEFAULT_MODEL

    # Job kicked off against the resolved catalog original, writing under produced/.
    stem_set_id, source_path, output_dir, model_name = captured["args"]
    assert source_path == str(audio_library / "5_test-track.mp3")
    assert produce.PRODUCED_SUBDIR in output_dir
    assert str(stem_set_id) in output_dir


def test_separate_unknown_song_returns_404(stem_client, monkeypatch):
    client, *_ = stem_client
    monkeypatch.setattr(stem_jobs.manager, "start", lambda *a, **k: None)
    resp = client.post(
        "/api/produce/stems/separate",
        json={"song_id": 9999},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 404


def test_list_stems_reports_status_and_stems(stem_client, monkeypatch):
    client, db, _ = stem_client
    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))
    await_run(db.set_stem_set_status(stem_set["id"], "complete"))
    await_run(db.add_stem(stem_set["id"], "vocals", "/app/audio_library/produced/5/stems/1/vocals.wav"))

    resp = client.get(
        "/api/produce/songs/5/stems", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 200
    sets = resp.json()["stem_sets"]
    assert len(sets) == 1
    assert sets[0]["status"] == "complete"
    assert [s["name"] for s in sets[0]["stems"]] == ["vocals"]


def test_stream_stem_serves_file(stem_client, monkeypatch, tmp_path):
    client, db, _ = stem_client
    stem_file = tmp_path / "vocals.wav"
    _write_tone(stem_file, 220.0)
    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))
    stem = await_run(db.add_stem(stem_set["id"], "vocals", str(stem_file)))

    resp = client.get(
        f"/api/produce/stems/{stem['id']}/audio",
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200
    assert resp.content == stem_file.read_bytes()


def test_render_requires_complete_set(stem_client, monkeypatch):
    client, db, _ = stem_client
    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))  # still 'queued'
    resp = client.post(
        f"/api/produce/stems/{stem_set['id']}/render",
        json={},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 409


def test_render_produces_candidate_under_produced(stem_client, monkeypatch, tmp_path):
    client, db, _ = stem_client
    vocals = tmp_path / "vocals.wav"
    drums = tmp_path / "drums.wav"
    _write_tone(vocals, 220.0)
    _write_tone(drums, 440.0)

    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))
    await_run(db.set_stem_set_status(stem_set["id"], "complete"))
    await_run(db.add_stem(stem_set["id"], "vocals", str(vocals)))
    await_run(db.add_stem(stem_set["id"], "drums", str(drums)))

    resp = client.post(
        f"/api/produce/stems/{stem_set['id']}/render",
        json={"adjustments": {"drums": {"mute": True}}},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200, resp.text
    candidate = Path(resp.json()["candidate_path"])
    # Candidate lands under produced/ so it plugs into approve()/discard() as-is.
    assert produce.PRODUCED_SUBDIR in str(candidate)
    assert candidate.exists()


@pytest.mark.asyncio
async def test_job_failure_records_failed_status(monkeypatch, tmp_path):
    """A separator exception marks the stem set 'failed' (not silently swallowed)."""
    db = FakeDB()
    stem_set = await db.create_stem_set(5, "htdemucs_6s")

    def boom(*args, **kwargs):
        raise RuntimeError("demucs blew up")

    monkeypatch.setattr(stem_separation, "separate_stems", boom)

    await stem_jobs.manager._run(
        stem_set["id"], "src.wav", str(tmp_path / "out"), "htdemucs_6s", db
    )

    assert db.stem_sets[stem_set["id"]]["status"] == "failed"
    assert "demucs blew up" in db.stem_sets[stem_set["id"]]["error"]


def await_run(coro):
    """Drive a coroutine to completion from sync test-setup code.

    The FakeDB methods don't touch real I/O, so a throwaway loop is enough and
    avoids interfering with the TestClient's own event loop.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
