"""Whisper's invented lines are dropped from a transcript; sung lines are kept."""

import pytest

from src.rag.lyrics_extractor import is_phantom_segment


@pytest.mark.parametrize(
    "text",
    [
        "Thank you.",
        " Thank you very much!",
        "Thanks for watching!",
        "© transcript Emily Beynon",
        "Subtitles by the Amara.org community",
        "you",
        "...",
    ],
)
def test_phantom_lines_are_dropped(text):
    assert is_phantom_segment(text)


@pytest.mark.parametrize(
    "text",
    [
        "Buckets of rain, buckets of tears",
        "Thank you for loving me",
        "I said thank you, baby, and walked away",
    ],
)
def test_sung_lines_are_kept(text):
    assert not is_phantom_segment(text)


def test_quiet_stem_is_brought_up_for_whisper(tmp_path):
    """A stem recorded quietly reaches Whisper at full level, not as near-silence."""
    import numpy as np
    import soundfile as sf

    from src.rag.lyrics_extractor import _peak_normalized

    path = tmp_path / "quiet.wav"
    tone = 0.25 * np.sin(np.linspace(0, 2 * np.pi * 440, 16000))
    sf.write(path, tone, 16000)

    assert np.abs(_peak_normalized(str(path))).max() == pytest.approx(0.89, abs=0.01)
