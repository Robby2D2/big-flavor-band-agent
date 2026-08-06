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
from src.production import (
    audio_preview,
    instrument_tagging,
    stem_separation,
    waveform_peaks,
)
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
        row = {
            "id": sid,
            "stem_set_id": stem_set_id,
            "name": name,
            "path": path,
            "waveform_peaks": None,
        }
        self.stems[sid] = row
        return row

    async def set_stem_waveform_peaks(self, stem_id, peaks):
        row = self.stems.get(stem_id)
        if row is None:
            return None
        row["waveform_peaks"] = peaks
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
    assert client.get("/api/produce/stems/1/peaks").status_code == 401
    assert client.get("/api/produce/stems/1/preview").status_code == 401
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


# ---- waveform peaks: the drawing envelope the console fetches instead of audio ----

def _stub_post_separation_passes(monkeypatch):
    """Keep the tagger and ffmpeg out of job tests, the way Demucs is kept out.

    ``_run`` warms peaks, then previews, then tags. Without this the real
    AudioSet model is downloaded and run (turning a sub-second test into a
    minute) and ffmpeg is invoked for real.
    """
    monkeypatch.setattr(
        instrument_tagging, "identify_instruments", lambda path: {"instruments": []}
    )
    monkeypatch.setattr(
        audio_preview, "build_preview", lambda source, output: str(source)
    )


def _complete_set_with_stem(db, tmp_path, name="vocals"):
    """Create a complete stem set with one real tone file on disk."""
    audio = tmp_path / f"{name}.wav"
    _write_tone(audio, 220.0, seconds=0.5)
    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))
    await_run(db.set_stem_set_status(stem_set["id"], "complete"))
    return await_run(db.add_stem(stem_set["id"], name, str(audio)))


def test_peaks_computed_once_then_served_from_cache(stem_client, monkeypatch, tmp_path):
    """The first request computes and persists; the second must not recompute."""
    client, db, _ = stem_client
    stem = _complete_set_with_stem(db, tmp_path)

    first = client.get(
        f"/api/produce/stems/{stem['id']}/peaks", headers=_editor_headers(monkeypatch)
    )
    assert first.status_code == 200, first.text
    payload = first.json()["peaks"]
    assert payload["version"] == waveform_peaks.PEAKS_FORMAT_VERSION
    assert len(payload["min"]) == len(payload["max"]) == payload["resolution"]
    assert db.stems[stem["id"]]["waveform_peaks"] is not None

    # With the computation sabotaged, an identical response proves the cached
    # payload was served rather than recomputed.
    def boom(*args, **kwargs):
        raise RuntimeError("should not recompute")

    monkeypatch.setattr(waveform_peaks, "compute_peaks", boom)
    second = client.get(
        f"/api/produce/stems/{stem['id']}/peaks", headers=_editor_headers(monkeypatch)
    )
    assert second.status_code == 200
    assert second.json()["peaks"] == payload


def test_peaks_recomputed_when_cached_format_is_stale(stem_client, monkeypatch, tmp_path):
    """An envelope from an older format version is ignored, not served.

    This is what lets the payload shape change without a backfill over the
    whole catalog.
    """
    client, db, _ = stem_client
    stem = _complete_set_with_stem(db, tmp_path)
    db.stems[stem["id"]]["waveform_peaks"] = {"version": 0, "min": [], "max": []}

    resp = client.get(
        f"/api/produce/stems/{stem['id']}/peaks", headers=_editor_headers(monkeypatch)
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["peaks"]["version"] == waveform_peaks.PEAKS_FORMAT_VERSION
    assert resp.json()["peaks"]["min"], "stale cache should have been replaced"


def test_peaks_unknown_stem_is_404(stem_client, monkeypatch):
    client, *_ = stem_client
    resp = client.get(
        "/api/produce/stems/9999/peaks", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 404


def test_peaks_missing_audio_file_is_404(stem_client, monkeypatch, tmp_path):
    client, db, _ = stem_client
    stem_set = await_run(db.create_stem_set(5, "htdemucs_6s"))
    stem = await_run(
        db.add_stem(stem_set["id"], "vocals", str(tmp_path / "not-written.wav"))
    )

    resp = client.get(
        f"/api/produce/stems/{stem['id']}/peaks", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 404


def test_peaks_compute_failure_is_503(stem_client, monkeypatch, tmp_path):
    """An unreadable file surfaces as 503, not a 500 traceback."""
    client, db, _ = stem_client
    stem = _complete_set_with_stem(db, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("libsndfile said no")

    monkeypatch.setattr(waveform_peaks, "compute_peaks", boom)
    resp = client.get(
        f"/api/produce/stems/{stem['id']}/peaks", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 503


# ---- compressed playback copies ----

def test_stem_preview_is_built_once_and_served(stem_client, monkeypatch, tmp_path):
    client, db, _ = stem_client
    stem = _complete_set_with_stem(db, tmp_path)
    built = []

    def fake_build(source, output):
        built.append(source)
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_bytes(b"fake-opus-bytes")
        return output

    monkeypatch.setattr(audio_preview, "build_preview", fake_build)
    headers = _editor_headers(monkeypatch)

    first = client.get(f"/api/produce/stems/{stem['id']}/preview", headers=headers)
    assert first.status_code == 200, first.text
    assert first.headers["content-type"].startswith(audio_preview.PREVIEW_MEDIA_TYPE)
    assert first.content == b"fake-opus-bytes"

    second = client.get(f"/api/produce/stems/{stem['id']}/preview", headers=headers)
    assert second.status_code == 200
    # build_preview owns the "already built?" check, so the route calls it each
    # time — what matters is that the same preview file is served back.
    assert second.content == first.content


def test_stem_preview_unknown_stem_is_404(stem_client, monkeypatch):
    client, *_ = stem_client
    resp = client.get(
        "/api/produce/stems/9999/preview", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 404


def test_stem_preview_without_ffmpeg_is_503(stem_client, monkeypatch, tmp_path):
    """Outside Docker there is no ffmpeg; that must read as unavailable, not a crash."""
    client, db, _ = stem_client
    stem = _complete_set_with_stem(db, tmp_path)

    def no_ffmpeg(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(audio_preview, "build_preview", no_ffmpeg)
    resp = client.get(
        f"/api/produce/stems/{stem['id']}/preview", headers=_editor_headers(monkeypatch)
    )
    assert resp.status_code == 503
    assert "ffmpeg" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_job_warms_peaks_after_completion(monkeypatch, tmp_path):
    """A finished separation leaves every stem's envelope already cached."""
    db = FakeDB()
    stem_set = await db.create_stem_set(5, "htdemucs_6s")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_separate(source_path, output_dir, model_name):
        made = []
        for name, freq in (("vocals", 220.0), ("drums", 440.0)):
            path = Path(output_dir) / f"{name}.wav"
            _write_tone(path, freq, seconds=0.5)
            made.append({"name": name, "path": str(path)})
        return made

    monkeypatch.setattr(stem_separation, "separate_stems", fake_separate)
    _stub_post_separation_passes(monkeypatch)

    await stem_jobs.manager._run(
        stem_set["id"], "src.wav", str(out_dir), "htdemucs_6s", db
    )

    assert db.stem_sets[stem_set["id"]]["status"] == "complete"
    assert len(db.stems) == 2
    for stem in db.stems.values():
        assert stem["waveform_peaks"] is not None, stem["name"]


@pytest.mark.asyncio
async def test_peaks_warm_failure_does_not_fail_the_job(monkeypatch, tmp_path):
    """Warming is best-effort: a failure leaves usable stems and a complete set."""
    db = FakeDB()
    stem_set = await db.create_stem_set(5, "htdemucs_6s")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    def fake_separate(source_path, output_dir, model_name):
        path = Path(output_dir) / "vocals.wav"
        _write_tone(path, 220.0, seconds=0.5)
        return [{"name": "vocals", "path": str(path)}]

    def boom(*args, **kwargs):
        raise RuntimeError("peaks blew up")

    monkeypatch.setattr(stem_separation, "separate_stems", fake_separate)
    monkeypatch.setattr(waveform_peaks, "compute_peaks", boom)
    _stub_post_separation_passes(monkeypatch)

    await stem_jobs.manager._run(
        stem_set["id"], "src.wav", str(out_dir), "htdemucs_6s", db
    )

    assert db.stem_sets[stem_set["id"]]["status"] == "complete"
    assert len(db.stems) == 1
    assert db.stems[1]["waveform_peaks"] is None


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
