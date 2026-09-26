"""Tests for session transcription (src/production/session_transcribe.py).

Only the part that can be wrong without anyone noticing: Whisper times a region
from the start of the *clip* it was given, while every take boundary is a
position on the **session timeline**. Getting that offset wrong misplaces every
attempt in the session by however far into the recording the region sat — a
silent, systematic error, so it gets a test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production.session_detect import Take  # noqa: E402
from src.production.session_transcribe import transcribe_region  # noqa: E402


class FakeExtractor:
    """Stands in for LyricsExtractor, returning clip-relative segments."""

    def __init__(self, result):
        self.result = result
        self.calls = []

    def transcribe_audio(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return self.result


def test_segment_times_are_moved_onto_the_session_timeline():
    extractor = FakeExtractor(
        {
            "segments": [
                {"start": 0.0, "end": 4.0, "text": "first line", "confidence": 0.9},
                {"start": 10.5, "end": 14.0, "text": "second line", "confidence": 0.8},
            ]
        }
    )
    region = Take(start=13376.1, end=13500.0)

    lines = transcribe_region("vocals.wav", region, extractor)

    assert [line.start for line in lines] == [13376.1, 13386.6]
    assert [line.end for line in lines] == [13380.1, 13390.1]
    assert [line.text for line in lines] == ["first line", "second line"]


def test_empty_segments_are_dropped():
    extractor = FakeExtractor(
        {
            "segments": [
                {"start": 0.0, "end": 1.0, "text": "   ", "confidence": 0.9},
                {"start": 2.0, "end": 3.0, "text": "real", "confidence": 0.9},
            ]
        }
    )

    lines = transcribe_region("vocals.wav", Take(0, 10), extractor)

    assert [line.text for line in lines] == ["real"]


def test_a_failed_transcription_yields_no_lines_rather_than_raising():
    """A region we cannot read is a region a human splits, not a crash."""
    extractor = FakeExtractor({"error": "faster-whisper not available", "segments": []})

    assert transcribe_region("vocals.wav", Take(0, 10), extractor) == []


def test_voice_detection_is_on_so_chatter_lands_in_its_own_line():
    extractor = FakeExtractor({"segments": []})

    transcribe_region("vocals.wav", Take(0, 10), extractor)

    _, kwargs = extractor.calls[0]
    assert kwargs["vad_filter"] is True
    assert kwargs["vad_min_silence_ms"] == 1500
