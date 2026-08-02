"""Tests for the lyric-extraction job runner (follow-along timings).

Covers the two behaviours added alongside timed lyrics, without loading Whisper
or Demucs (``_blocking_extract`` is stubbed throughout):
  - transcription prefers isolated vocals — an already-separated ``vocals`` stem
    is reused when it exists on disk, and never when the recorded file is gone,
  - the per-line timings Whisper returns are persisted, having previously been
    discarded in favour of the joined text.
"""
import pytest

from src.api import lyrics_jobs


class FakeRag:
    def __init__(self):
        self.text_embedding_model = None
        self.stored = []

    async def store_text_embedding(self, song_id, content_type, content, embedding):
        self.stored.append((song_id, content_type, content))


class FakeDB:
    def __init__(self, vocals_path=None):
        self._vocals_path = vocals_path
        self.saved_timings = []

    async def get_vocals_stem_path(self, song_id):
        return self._vocals_path

    async def save_lyric_timings(
        self, song_id, lines, source="whisper", model=None,
        audio_source="mix", format_version=1,
    ):
        row = {
            "song_id": song_id, "lines": lines, "source": source,
            "model": model, "audio_source": audio_source,
            "format_version": format_version, "status": "current",
        }
        self.saved_timings.append(row)
        return row


_RESULT = {
    "lyrics": "Headed down south",
    "lines": [{"start": 2.0, "end": 5.0, "text": "Headed down south"}],
    "audio_source": lyrics_jobs.AUDIO_SOURCE_VOCALS,
    "model": lyrics_jobs.WHISPER_MODEL,
}


def _stub_extract(monkeypatch, calls, result=None):
    """Replace the Whisper/Demucs call with a recorder."""
    def fake(audio_path, min_confidence=0.5, vocals_path=None, separate_vocals=True,
             word_timestamps=True):
        calls.append({
            "audio_path": audio_path,
            "vocals_path": vocals_path,
            "separate_vocals": separate_vocals,
        })
        return result or _RESULT

    monkeypatch.setattr(lyrics_jobs, "_blocking_extract", fake)


@pytest.mark.asyncio
async def test_reuses_existing_vocals_stem(monkeypatch, tmp_path):
    stem = tmp_path / "vocals.wav"
    stem.write_bytes(b"vocal-audio")

    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()
    db = FakeDB(vocals_path=str(stem))

    await manager._run(5, "/audio/5.mp3", FakeRag(), db)

    assert manager.status(5)["status"] == lyrics_jobs.STATUS_COMPLETE
    # The stem was handed to the transcriber, so no Demucs run was needed.
    assert calls[0]["vocals_path"] == str(stem)


@pytest.mark.asyncio
async def test_separates_when_recorded_stem_is_missing_on_disk(monkeypatch, tmp_path):
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()
    # A path the DB knows about but that no longer exists (cleaned-up produced/).
    db = FakeDB(vocals_path=str(tmp_path / "gone.wav"))

    await manager._run(5, "/audio/5.mp3", FakeRag(), db)

    assert calls[0]["vocals_path"] is None
    assert calls[0]["separate_vocals"] is True


@pytest.mark.asyncio
async def test_separates_when_song_has_no_stems(monkeypatch):
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()

    await manager._run(5, "/audio/5.mp3", FakeRag(), FakeDB(vocals_path=None))

    assert calls[0]["vocals_path"] is None
    assert calls[0]["separate_vocals"] is True


@pytest.mark.asyncio
async def test_persists_timings_and_text(monkeypatch):
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()
    rag, db = FakeRag(), FakeDB()

    await manager._run(5, "/audio/5.mp3", rag, db)

    # Lyric text still lands in text_embeddings (the search source of truth)...
    assert rag.stored == [(5, "lyrics", "Headed down south")]
    # ...and the timings Whisper returned are no longer thrown away.
    assert len(db.saved_timings) == 1
    saved = db.saved_timings[0]
    assert saved["lines"][0]["text"] == "Headed down south"
    assert saved["audio_source"] == lyrics_jobs.AUDIO_SOURCE_VOCALS
    assert saved["model"] == lyrics_jobs.WHISPER_MODEL


@pytest.mark.asyncio
async def test_runs_without_a_db_handle(monkeypatch):
    """db is optional — the job degrades to the old text-only behaviour."""
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()
    rag = FakeRag()

    await manager._run(5, "/audio/5.mp3", rag, None)

    assert manager.status(5)["status"] == lyrics_jobs.STATUS_COMPLETE
    assert rag.stored == [(5, "lyrics", "Headed down south")]
    assert calls[0]["vocals_path"] is None


@pytest.mark.asyncio
async def test_no_lyrics_detected_fails_without_writing_timings(monkeypatch):
    calls = []
    _stub_extract(monkeypatch, calls, result={**_RESULT, "lyrics": ""})
    manager = lyrics_jobs.LyricsJobManager()
    db = FakeDB()

    await manager._run(5, "/audio/5.mp3", FakeRag(), db)

    status = manager.status(5)
    assert status["status"] == lyrics_jobs.STATUS_FAILED
    assert status["error"] == "No lyrics detected"
    assert db.saved_timings == []


def test_timings_text_rebuilds_the_transcript():
    lines = [
        {"start": 0.0, "end": 1.0, "text": "Headed down south"},
        {"start": 1.0, "end": 2.0, "text": "to the pines"},
    ]
    assert lyrics_jobs.timings_text(lines) == "Headed down south to the pines"


def test_timings_view_decodes_raw_jsonb_lines():
    """Some DatabaseManager methods hand back the raw JSONB string."""
    view = lyrics_jobs.timings_view({
        "format_version": 1, "source": "whisper", "model": "large-v3",
        "audio_source": "vocals_stem", "status": "stale",
        "lines": '[{"start": 1.0, "end": 2.0, "text": "hi"}]',
    })
    assert view["lines"] == [{"start": 1.0, "end": 2.0, "text": "hi"}]
    assert view["status"] == "stale"


def test_timings_view_of_nothing_is_none():
    assert lyrics_jobs.timings_view(None) is None
