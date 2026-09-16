"""Tests for lyric chunking (src/rag/lyric_chunks.py).

Pure text splitting. The cases that matter are the degenerate ones: empty
lyrics must not produce an empty chunk (which would embed as noise and match
everything), and a short tail must not stand alone as a thin vector.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.lyric_chunks import (  # noqa: E402
    MIN_TAIL_WORDS,
    OVERLAP_WORDS,
    WORDS_PER_CHUNK,
    chunk_lyrics,
)


def words(count: int) -> str:
    return " ".join(f"w{i}" for i in range(count))


def test_empty_lyrics_produce_no_chunks():
    """An empty chunk would embed as noise and match everything."""
    assert chunk_lyrics("") == []
    assert chunk_lyrics("   \n  ") == []
    assert chunk_lyrics(None) == []


def test_lyrics_shorter_than_a_window_stay_whole():
    assert chunk_lyrics("just a few words here") == ["just a few words here"]


def test_a_long_lyric_is_split():
    chunks = chunk_lyrics(words(200))
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_chunks_are_about_one_window_long():
    for chunk in chunk_lyrics(words(200)):
        assert len(chunk.split()) <= WORDS_PER_CHUNK


def test_chunks_overlap_so_a_line_is_never_split_across_both():
    chunks = chunk_lyrics(words(200))
    first_words = chunks[0].split()
    second_words = chunks[1].split()
    shared = set(first_words) & set(second_words)
    assert len(shared) == OVERLAP_WORDS


def test_every_word_survives_somewhere():
    source = words(200)
    covered = set()
    for chunk in chunk_lyrics(source):
        covered.update(chunk.split())
    assert covered == set(source.split())


def test_a_short_tail_is_folded_in_rather_than_left_alone():
    """A five-word final chunk is a thin vector that matches poorly."""
    for total in range(WORDS_PER_CHUNK + 1, WORDS_PER_CHUNK * 3):
        chunks = chunk_lyrics(words(total))
        if len(chunks) > 1:
            assert len(chunks[-1].split()) >= MIN_TAIL_WORDS, total


def test_whitespace_is_normalised():
    assert chunk_lyrics("  one   two \n three  ") == ["one two three"]


def test_a_real_length_lyric_yields_a_handful_of_chunks():
    """850 characters is this catalogue's average lyric."""
    chunks = chunk_lyrics(" ".join(["word"] * 150))
    assert 2 <= len(chunks) <= 6
