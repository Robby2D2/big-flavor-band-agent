"""A line's start lands on the voice, not on the silence Whisper stretched it over."""

from types import SimpleNamespace

import numpy as np
import pytest

from src.api import lyrics_jobs
from src.rag import lyrics_extractor
from src.rag.lyrics_extractor import LyricsExtractor, snap_line_starts

RATE = 16000


def _vocal(*sung, seconds=6.0):
    """Silence with a tone over each ``(start, end, level)`` span."""
    audio = np.zeros(int(seconds * RATE), dtype=np.float32)
    for start, end, level in sung:
        a, b = int(start * RATE), int(end * RATE)
        audio[a:b] = level * np.sin(2 * np.pi * 220 * np.arange(b - a) / RATE)
    return audio


def _line(*words):
    return {
        "start": words[0][0],
        "end": words[-1][1],
        "text": "x",
        "words": [{"start": s, "end": e, "text": "x"} for s, e in words],
    }


def test_a_first_word_stretched_over_silence_moves_to_the_voice():
    lines = [_line((1.0, 2.0), (2.0, 2.5))]

    assert snap_line_starts(lines, _vocal((1.6, 2.5, 0.5))) == 1

    # The voice arrives at 1.6; the start stops just short of it.
    assert lines[0]["start"] == pytest.approx(1.55, abs=0.03)
    assert lines[0]["words"][0]["start"] == lines[0]["start"]
    assert lines[0]["words"][1]["start"] == 2.0
    assert lines[0]["end"] == 2.5


def test_a_word_sung_on_time_stays_put():
    lines = [_line((1.0, 2.0))]

    assert snap_line_starts(lines, _vocal((1.0, 2.0, 0.5))) == 0

    assert lines[0]["start"] == 1.0


def test_a_short_lead_in_is_left_as_ordinary_attack():
    lines = [_line((1.0, 2.0))]

    assert snap_line_starts(lines, _vocal((1.1, 2.0, 0.5))) == 0


def test_a_word_too_quiet_to_place_stays_put():
    lines = [_line((1.0, 2.0)), _line((3.0, 4.0))]

    moved = snap_line_starts(lines, _vocal((1.6, 2.0, 0.005), (3.0, 5.0, 0.5)))

    assert moved == 0
    assert lines[0]["start"] == 1.0


def test_a_word_sung_at_its_very_end_keeps_some_length():
    lines = [_line((1.0, 2.0))]

    snap_line_starts(lines, _vocal((1.98, 2.5, 0.5)))

    assert lines[0]["start"] <= 1.9


def test_a_second_pass_finds_nothing_left_to_move():
    lines = [_line((1.0, 2.0))]
    audio = _vocal((1.6, 2.5, 0.5))

    snap_line_starts(lines, audio)
    start = lines[0]["start"]

    assert snap_line_starts(lines, audio) == 0
    assert lines[0]["start"] == start


def test_lines_without_word_timings_are_skipped():
    lines = [{"start": 1.0, "end": 2.0, "text": "x"}]

    assert snap_line_starts(lines, _vocal((1.6, 2.5, 0.5))) == 0


def test_silent_or_empty_audio_moves_nothing():
    assert snap_line_starts([_line((1.0, 2.0))], np.zeros(RATE * 3, dtype=np.float32)) == 0
    assert snap_line_starts([_line((1.0, 2.0))], np.zeros(0, dtype=np.float32)) == 0


# --- wiring -----------------------------------------------------------------


def _extractor(monkeypatch):
    monkeypatch.setattr(lyrics_extractor, "FASTER_WHISPER_AVAILABLE", True)
    monkeypatch.setattr(lyrics_extractor, "_peak_normalized", lambda _p: _vocal((1.6, 2.5, 0.5)))
    word = SimpleNamespace(start=1.0, end=2.0, word=" Headed", probability=0.9)
    segment = SimpleNamespace(
        start=1.0, end=2.0, text=" Headed", avg_logprob=-0.1, words=[word]
    )
    info = SimpleNamespace(language="en", language_probability=1.0)
    extractor = LyricsExtractor.__new__(LyricsExtractor)
    extractor.min_confidence = 0.5
    extractor.whisper_model = SimpleNamespace(
        transcribe=lambda *_a, **_k: (iter([segment]), info)
    )
    return extractor


def test_transcribing_isolated_vocals_snaps_the_line(monkeypatch):
    result = _extractor(monkeypatch).extract_lyrics(
        "vocals.wav", word_timestamps=True, vocals_isolated=True
    )

    assert result["segments"][0]["start"] == pytest.approx(1.55, abs=0.03)


def test_transcribing_a_full_mix_keeps_whispers_times(monkeypatch):
    result = _extractor(monkeypatch).extract_lyrics("mix.mp3", word_timestamps=True)

    assert result["segments"][0]["start"] == 1.0


class _TimingsDB:
    def __init__(self, tmp_path, status="current", has_stem=True, edited_during_run=False):
        self.path = tmp_path / "vocals.wav"
        self.path.write_bytes(b"audio")
        self.record = {
            "status": status, "lines": [_line((1.0, 2.0))], "source": "whisper",
            "model": "large-v3", "audio_source": "vocals_stem", "format_version": 1,
            "updated_at": 1,
        }
        self.has_stem = has_stem
        self.edited_during_run = edited_during_run
        self.reads = 0
        self.saved = []

    async def get_lyric_timings(self, song_id):
        self.reads += 1
        if self.edited_during_run and self.reads > 1:
            return {**self.record, "updated_at": 2}
        return self.record

    async def list_stem_sets(self, song_id):
        if not self.has_stem:
            return []
        return [{"id": 1, "source_version_id": None, "status": "complete"}]

    async def list_stems(self, stem_set_id):
        return [{"id": 10, "name": "vocals", "display_name": None, "path": str(self.path)}]

    async def save_lyric_timings(self, song_id, lines, **kwargs):
        self.saved.append((song_id, lines, kwargs))


@pytest.fixture
def decoded(monkeypatch):
    monkeypatch.setattr(
        lyrics_extractor, "decode_audio",
        lambda _p, sampling_rate: _vocal((1.6, 2.5, 0.5)), raising=False,
    )


@pytest.mark.asyncio
async def test_stored_timings_are_corrected_and_keep_their_provenance(tmp_path, decoded):
    db = _TimingsDB(tmp_path)

    summary = await lyrics_jobs.snap_stored_timings(5, db)

    assert summary["moved"] == 1
    assert summary["shifts"] == [pytest.approx(0.55, abs=0.03)]
    song_id, lines, kwargs = db.saved[0]
    assert song_id == 5
    assert lines[0]["start"] == pytest.approx(1.55, abs=0.03)
    assert kwargs == {
        "source": "whisper", "model": "large-v3",
        "audio_source": "vocals_stem", "format_version": 1,
    }


@pytest.mark.asyncio
async def test_a_dry_run_writes_nothing(tmp_path, decoded):
    db = _TimingsDB(tmp_path)

    summary = await lyrics_jobs.snap_stored_timings(5, db, dry_run=True)

    assert summary["moved"] == 1
    assert db.saved == []


@pytest.mark.asyncio
async def test_stale_timings_are_left_alone(tmp_path, decoded):
    db = _TimingsDB(tmp_path, status="stale")

    assert await lyrics_jobs.snap_stored_timings(5, db) is None
    assert db.saved == []


class _Separator:
    def __init__(self, result):
        self.result = result
        self.heard = []

    def separate_vocals(self, audio_path, output_dir):
        self.heard.append(audio_path)
        return self.result


@pytest.mark.asyncio
async def test_a_song_with_no_stem_is_separated_first(tmp_path, decoded):
    db = _TimingsDB(tmp_path, has_stem=False)
    separator = _Separator(str(tmp_path / "separated.wav"))

    summary = await lyrics_jobs.snap_stored_timings(
        5, db, audio_path="song.mp3", extractor=separator
    )

    assert separator.heard == ["song.mp3"]
    assert summary["moved"] == 1
    assert len(db.saved) == 1


@pytest.mark.asyncio
async def test_a_song_with_no_stem_is_skipped_without_a_separator(tmp_path, decoded):
    db = _TimingsDB(tmp_path, has_stem=False)

    assert await lyrics_jobs.snap_stored_timings(5, db) is None
    assert db.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, "song.mp3"])
async def test_failed_separation_never_reads_the_mix(tmp_path, decoded, result):
    db = _TimingsDB(tmp_path, has_stem=False)

    with pytest.raises(RuntimeError, match="separation failed"):
        await lyrics_jobs.snap_stored_timings(
            5, db, audio_path="song.mp3", extractor=_Separator(result)
        )

    assert db.saved == []


@pytest.mark.asyncio
async def test_an_edit_made_during_the_run_is_not_overwritten(tmp_path, decoded):
    db = _TimingsDB(tmp_path, edited_during_run=True)

    await lyrics_jobs.snap_stored_timings(5, db)

    assert db.saved == []


def test_the_ledger_round_trips_and_tolerates_damage(tmp_path):
    from scripts.snap_lyric_timings import load_done, save_done

    ledger = tmp_path / "done.json"
    assert load_done(ledger) == set()

    save_done(ledger, {3, 1})
    assert load_done(ledger) == {1, 3}

    ledger.write_text("not json", encoding="utf-8")
    assert load_done(ledger) == set()
