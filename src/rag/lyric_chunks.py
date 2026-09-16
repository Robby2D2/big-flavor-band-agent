"""Splitting lyrics into verse-sized pieces for semantic search.

A whole song's lyrics averaged into one embedding is the wrong shape for the
question "which songs are about X". At 850 characters on average, a single
mention of the ocean is diluted to nothing. Chunks put each passage on its own
footing, so a song is found by the part of it that actually matches — and that
same passage is what gets shown to the evaluator as evidence.

Pure: no DB, no model. ``scripts/backfill_lyric_chunks.py`` embeds what this
produces.
"""
from __future__ import annotations

from typing import List

# Roughly a verse. Long enough to carry meaning, short enough that one subject
# dominates the vector rather than being averaged away.
WORDS_PER_CHUNK = 45

# Overlap so a line spanning a boundary still lands whole in one chunk.
OVERLAP_WORDS = 12

# Below this, a trailing fragment is folded into the previous chunk instead of
# standing as its own thin, noisy vector.
MIN_TAIL_WORDS = 15


def chunk_lyrics(
    text: str,
    words_per_chunk: int = WORDS_PER_CHUNK,
    overlap: int = OVERLAP_WORDS,
) -> List[str]:
    """Split lyrics into overlapping, verse-sized chunks.

    Returns an empty list for empty input, and a single chunk for lyrics shorter
    than one window — never an empty-string chunk, which would embed as noise.
    """
    if not text or not text.strip():
        return []

    words = text.split()
    if len(words) <= words_per_chunk:
        return [" ".join(words)]

    step = max(1, words_per_chunk - overlap)
    chunks: List[str] = []

    for start in range(0, len(words), step):
        window = words[start:start + words_per_chunk]
        if not window:
            break

        # A short tail belongs to the chunk before it rather than alone.
        remaining = len(words) - start
        if chunks and remaining < MIN_TAIL_WORDS:
            break

        chunks.append(" ".join(window))

        if start + words_per_chunk >= len(words):
            break

    return chunks
