"""Tests for the lyric-extraction job runner (follow-along timings).

Covers the behaviours added alongside timed lyrics, without loading Whisper or
Demucs (``_blocking_extract`` is stubbed except where mixing is under test):
  - transcription prefers isolated vocals — already-separated vocal stems are
    reused when they exist on disk, and never when the recorded file is gone,
  - with several vocal stems (one per mic) every vocal-named one is used by
    default, the editor can pick others, and they come from the stem set of the
    version being transcribed rather than the newest set of any take,
  - the per-line timings Whisper returns are persisted, having previously been
    discarded in favour of the joined text.
"""
import numpy as np
import pytest
import soundfile as sf

from src.api import lyrics_jobs


class FakeRag:
    def __init__(self):
        self.text_embedding_model = None
        self.stored = []

    async def index_text_content(self, song_id, content_type, content, embedding):
        self.stored.append((song_id, content_type, content))


class FakeDB:
    """Stem sets are ``{"id", "source_version_id", "status", "stems": [...]}``,
    listed newest first like ``DatabaseManager.list_stem_sets``."""

    def __init__(self, vocals_path=None, stem_sets=None):
        if stem_sets is None and vocals_path is not None:
            stem_sets = [_set(1, None, [_stem(10, "vocals", vocals_path)])]
        self._stem_sets = stem_sets or []
        self.saved_timings = []

    async def list_stem_sets(self, song_id):
        return [{k: v for k, v in s.items() if k != "stems"} for s in self._stem_sets]

    async def list_stems(self, stem_set_id):
        return next(s["stems"] for s in self._stem_sets if s["id"] == stem_set_id)

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


def _set(set_id, source_version_id, stems, status="complete"):
    return {
        "id": set_id, "source_version_id": source_version_id,
        "status": status, "stems": stems,
    }


def _stem(stem_id, name, path, display_name=None):
    return {"id": stem_id, "name": name, "path": str(path), "display_name": display_name}


def _files(tmp_path, *names):
    paths = []
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"audio")
        paths.append(path)
    return paths


def _stub_extract(monkeypatch, calls, result=None):
    """Replace the Whisper/Demucs call with a recorder."""
    def fake(audio_path, min_confidence=0.5, vocals_paths=(), separate_vocals=True,
             word_timestamps=True, extractor=None):
        calls.append({
            "audio_path": audio_path,
            "vocals_paths": list(vocals_paths),
            "separate_vocals": separate_vocals,
            "word_timestamps": word_timestamps,
            "extractor": extractor,
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
    assert calls[0]["vocals_paths"] == [str(stem)]


@pytest.mark.asyncio
async def test_separates_when_recorded_stem_is_missing_on_disk(monkeypatch, tmp_path):
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()
    # A path the DB knows about but that no longer exists (cleaned-up produced/).
    db = FakeDB(vocals_path=str(tmp_path / "gone.wav"))

    await manager._run(5, "/audio/5.mp3", FakeRag(), db)

    assert calls[0]["vocals_paths"] == []
    assert calls[0]["separate_vocals"] is True


@pytest.mark.asyncio
async def test_separates_when_song_has_no_stems(monkeypatch):
    calls = []
    _stub_extract(monkeypatch, calls)
    manager = lyrics_jobs.LyricsJobManager()

    await manager._run(5, "/audio/5.mp3", FakeRag(), FakeDB(vocals_path=None))

    assert calls[0]["vocals_paths"] == []
    assert calls[0]["separate_vocals"] is True


# ---- several vocal stems (a session song: one stem per mic) ----


@pytest.mark.asyncio
async def test_default_uses_every_vocal_stem(monkeypatch, tmp_path):
    """`vocals` is just the first mic in the session — often not the singer —
    so the default is every vocal-named stem, not that one alone."""
    kev, tom, guitar = _files(tmp_path, "vocals.flac", "vocals-2.flac", "guitar.flac")
    db = FakeDB(stem_sets=[_set(1, 95, [
        _stem(10, "guitar", guitar),
        _stem(11, "vocals", kev, "4 Kev Vox"),
        _stem(12, "vocals-2", tom, "8 Tom Vox"),
    ])])
    calls = []
    _stub_extract(monkeypatch, calls)

    await lyrics_jobs.extract_and_store(
        1000001, "/take.wav", FakeRag(), db, source_version_id=95
    )

    assert calls[0]["vocals_paths"] == [str(kev), str(tom)]


@pytest.mark.asyncio
async def test_default_matches_vocal_in_the_producers_label(tmp_path):
    """A stem the producer named "Lead vocal" counts even if Demucs called it other."""
    (other,) = _files(tmp_path, "other.flac")
    db = FakeDB(stem_sets=[_set(1, None, [_stem(10, "other", other, "Lead Vocal")])])

    assert await lyrics_jobs.resolve_vocals_paths(5, db) == [str(other)]


@pytest.mark.asyncio
async def test_editor_choice_overrides_the_default(tmp_path):
    kev, tom = _files(tmp_path, "vocals.flac", "vocals-2.flac")
    db = FakeDB(stem_sets=[_set(1, 95, [
        _stem(11, "vocals", kev), _stem(12, "vocals-2", tom),
    ])])

    paths = await lyrics_jobs.resolve_vocals_paths(1000001, db, 95, stem_ids=[12])

    assert paths == [str(tom)]


@pytest.mark.asyncio
async def test_empty_choice_means_the_full_mix(monkeypatch, tmp_path):
    (kev,) = _files(tmp_path, "vocals.flac")
    db = FakeDB(stem_sets=[_set(1, 95, [_stem(11, "vocals", kev)])])
    calls = []
    _stub_extract(monkeypatch, calls)

    await lyrics_jobs.extract_and_store(
        1000001, "/take.wav", FakeRag(), db, source_version_id=95, stem_ids=[]
    )

    assert calls[0]["vocals_paths"] == []
    assert calls[0]["separate_vocals"] is True


@pytest.mark.asyncio
async def test_stems_come_from_the_version_being_transcribed(tmp_path):
    """The newest set may belong to another take; its timings wouldn't line up."""
    published, other_take = _files(tmp_path, "pub.flac", "other.flac")
    db = FakeDB(stem_sets=[
        _set(48, 104, [_stem(20, "vocals", other_take)]),
        _set(39, 95, [_stem(11, "vocals", published)]),
    ])

    assert await lyrics_jobs.resolve_vocals_paths(1000001, db, 95) == [str(published)]


@pytest.mark.asyncio
async def test_session_song_without_a_matching_set_separates(tmp_path):
    (other_take,) = _files(tmp_path, "other.flac")
    db = FakeDB(stem_sets=[_set(48, 104, [_stem(20, "vocals", other_take)])])

    assert await lyrics_jobs.resolve_vocals_paths(1000001, db, 95) == []


@pytest.mark.asyncio
async def test_catalog_song_falls_back_to_its_newest_set(tmp_path):
    """Stems of a cleaned version still sit on the original's timeline."""
    (cleaned,) = _files(tmp_path, "cleaned.flac")
    db = FakeDB(stem_sets=[_set(3, 7, [_stem(30, "vocals", cleaned)])])

    assert await lyrics_jobs.resolve_vocals_paths(5, db, None) == [str(cleaned)]


@pytest.mark.asyncio
async def test_incomplete_sets_are_ignored(tmp_path):
    (stem,) = _files(tmp_path, "vocals.flac")
    db = FakeDB(stem_sets=[_set(1, 95, [_stem(11, "vocals", stem)], status="running")])

    assert await lyrics_jobs.resolve_vocals_paths(1000001, db, 95) == []


def test_several_stems_are_mixed_into_one_transcription(tmp_path):
    """Whisper hears both singers at once, never one mic at a time."""
    rate = 16000
    kev, tom = tmp_path / "vocals.wav", tmp_path / "vocals-2.wav"
    sf.write(str(kev), np.full(rate, 0.25, dtype="float32"), rate)
    sf.write(str(tom), np.full(rate, 0.5, dtype="float32"), rate)

    heard = {}

    class FakeExtractor:
        def is_available(self):
            return True

        def extract_lyrics(self, path, separate_vocals, word_timestamps):
            audio, sample_rate = sf.read(path)
            heard.update(path=path, audio=audio, rate=sample_rate,
                         separate=separate_vocals)
            return {"lyrics": "Headed down south", "segments": []}

    result = lyrics_jobs._blocking_extract(
        "/take.wav", vocals_paths=[str(kev), str(tom)], extractor=FakeExtractor()
    )

    assert heard["path"] not in (str(kev), str(tom))
    assert heard["rate"] == rate
    assert heard["audio"][0] == pytest.approx(0.75, abs=1e-4)
    assert heard["separate"] is False
    assert result["audio_source"] == lyrics_jobs.AUDIO_SOURCE_VOCALS


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
    assert calls[0]["vocals_paths"] == []


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


@pytest.mark.asyncio
async def test_extract_and_store_reuses_a_supplied_extractor(monkeypatch):
    """The backfill script loads Whisper once and hands it to every song."""
    calls = []
    _stub_extract(monkeypatch, calls)
    sentinel = object()

    summary = await lyrics_jobs.extract_and_store(
        5, "/audio/5.mp3", FakeRag(), FakeDB(), extractor=sentinel
    )

    assert calls[0]["extractor"] is sentinel
    assert summary["line_count"] == 1
    assert summary["audio_source"] == lyrics_jobs.AUDIO_SOURCE_VOCALS


@pytest.mark.asyncio
async def test_extract_and_store_always_asks_for_word_timestamps(monkeypatch):
    """Words are captured now so the catalog backfill never has to re-run."""
    calls = []
    _stub_extract(monkeypatch, calls)

    await lyrics_jobs.extract_and_store(5, "/audio/5.mp3", FakeRag(), FakeDB())

    assert calls[0]["word_timestamps"] is True


@pytest.mark.asyncio
async def test_extract_and_store_raises_on_empty_transcript(monkeypatch):
    """An empty transcript is a failure to report, not a result to store."""
    calls = []
    _stub_extract(monkeypatch, calls, result={**_RESULT, "lyrics": ""})
    db = FakeDB()

    with pytest.raises(RuntimeError, match="No lyrics detected"):
        await lyrics_jobs.extract_and_store(5, "/audio/5.mp3", FakeRag(), db)

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
