"""
Assert-based tests for SongRAGSystem.search_related_songs (issue #25).

These build a bare SongRAGSystem (no CLAP / sentence-transformers / DB load) and
stub get_song_embedding + search_by_embedding, so the more-like-this plumbing —
source-song exclusion, limit handling, and the no-embedding case — is tested
without a live database or any model/LLM call.
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.big_flavor_rag import SongRAGSystem


def make_rag(embedding_row, search_results):
    """Bare SongRAGSystem with the two collaborators of search_related_songs stubbed."""
    rag = SongRAGSystem.__new__(SongRAGSystem)

    async def fake_get_song_embedding(song_id):
        return embedding_row

    captured = {}

    async def fake_search_by_embedding(embedding, limit=10, similarity_threshold=0.5):
        captured["embedding"] = embedding
        captured["limit"] = limit
        return search_results

    rag.get_song_embedding = fake_get_song_embedding
    rag.search_by_embedding = fake_search_by_embedding
    rag._captured = captured
    return rag


@pytest.mark.asyncio
async def test_excludes_source_song_from_results():
    rag = make_rag(
        embedding_row={"combined_embedding": "[0.1,0.2]"},
        search_results=[
            {"song_id": 1, "title": "Source", "similarity": 1.0},
            {"song_id": 2, "title": "Other A", "similarity": 0.9},
            {"song_id": 3, "title": "Other B", "similarity": 0.8},
        ],
    )

    results = await rag.search_related_songs(song_id=1, limit=10)

    assert [r["song_id"] for r in results] == [2, 3]
    assert all(r["song_id"] != 1 for r in results)


@pytest.mark.asyncio
async def test_honors_limit_after_excluding_source():
    # search_by_embedding is asked for limit + 1 so dropping the source still
    # leaves a full `limit`-sized result set.
    rag = make_rag(
        embedding_row={"combined_embedding": "[0.1,0.2]"},
        search_results=[
            {"song_id": 1, "title": "Source", "similarity": 1.0},
            {"song_id": 2, "title": "A", "similarity": 0.9},
            {"song_id": 3, "title": "B", "similarity": 0.8},
        ],
    )

    results = await rag.search_related_songs(song_id=1, limit=2)

    assert rag._captured["limit"] == 3  # limit + 1
    assert len(results) == 2
    assert [r["song_id"] for r in results] == [2, 3]


@pytest.mark.asyncio
async def test_song_without_embedding_returns_empty():
    rag = make_rag(embedding_row=None, search_results=[])
    assert await rag.search_related_songs(song_id=99, limit=10) == []


@pytest.mark.asyncio
async def test_embedding_row_with_null_vector_returns_empty():
    rag = make_rag(embedding_row={"combined_embedding": None}, search_results=[])
    assert await rag.search_related_songs(song_id=42, limit=10) == []
