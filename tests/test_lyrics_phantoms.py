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
