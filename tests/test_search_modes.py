"""
Assert-based tests for the direct search modes exposed in issue #26
(tempo / audio-similarity / hybrid).

These call the FastAPI route handlers directly with a fake RAG system and a
fake DatabaseManager, so they verify the endpoint orchestration (input
validation + delegation to the RAG read seam) without a live database, LLM, or
audio model. They also cover the hybrid text+tempo helper on SongRAGSystem
using a fake DB pool.
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.routers import search as search_router
from src.api.dependencies import (
    TempoSearchRequest,
    AudioSimilaritySearchRequest,
    HybridSearchRequest,
)
from src.rag.big_flavor_rag import SongRAGSystem


class FakeRag:
    """Records calls and returns canned, deterministic results."""

    def __init__(self):
        self.calls = []

    async def search_by_tempo_range(self, min_tempo=None, max_tempo=None, limit=10):
        self.calls.append(("tempo", min_tempo, max_tempo, limit))
        return [{"id": 1, "title": "A", "tempo_bpm": 125.0}]

    async def search_related_songs(self, song_id, limit=10):
        self.calls.append(("audio", song_id, limit))
        return [{"id": 2, "title": "B", "similarity": 0.9}]

    async def search_text_with_tempo(
        self, description, min_tempo=None, max_tempo=None, limit=10
    ):
        self.calls.append(("hybrid", description, min_tempo, max_tempo, limit))
        return [{"id": 3, "title": "C", "tempo_bpm": 90.0}]


class FakeDb:
    def __init__(self, existing_song=True):
        self._existing = existing_song

    async def get_song(self, song_id):
        return {"id": song_id} if self._existing else None


@pytest.mark.asyncio
async def test_tempo_search_passes_bounds_through():
    rag = FakeRag()
    result = await search_router.search_by_tempo(
        TempoSearchRequest(min_bpm=120, max_bpm=130, limit=5), rag=rag
    )
    assert result == {"results": [{"id": 1, "title": "A", "tempo_bpm": 125.0}]}
    assert rag.calls == [("tempo", 120, 130, 5)]


@pytest.mark.asyncio
async def test_tempo_search_no_bounds_returns_empty_without_querying():
    rag = FakeRag()
    result = await search_router.search_by_tempo(
        TempoSearchRequest(min_bpm=None, max_bpm=None), rag=rag
    )
    assert result == {"results": []}
    assert rag.calls == []


@pytest.mark.asyncio
async def test_tempo_search_inverted_band_returns_empty_without_querying():
    rag = FakeRag()
    result = await search_router.search_by_tempo(
        TempoSearchRequest(min_bpm=140, max_bpm=100), rag=rag
    )
    assert result == {"results": []}
    assert rag.calls == []


@pytest.mark.asyncio
async def test_audio_search_delegates_to_related_songs():
    rag = FakeRag()
    db = FakeDb(existing_song=True)
    result = await search_router.search_by_audio(
        AudioSimilaritySearchRequest(song_id=42, limit=7), rag=rag, db=db
    )
    assert result == {"results": [{"id": 2, "title": "B", "similarity": 0.9}]}
    assert rag.calls == [("audio", 42, 7)]


@pytest.mark.asyncio
async def test_audio_search_unknown_song_404s():
    rag = FakeRag()
    db = FakeDb(existing_song=False)
    with pytest.raises(Exception) as exc:
        await search_router.search_by_audio(
            AudioSimilaritySearchRequest(song_id=999), rag=rag, db=db
        )
    # FastAPI HTTPException carries a 404 status code.
    assert getattr(exc.value, "status_code", None) == 404
    assert rag.calls == []


@pytest.mark.asyncio
async def test_hybrid_search_passes_query_and_band():
    rag = FakeRag()
    result = await search_router.search_hybrid(
        HybridSearchRequest(query="  calm  ", min_bpm=80, max_bpm=100, limit=4),
        rag=rag,
    )
    assert result == {"results": [{"id": 3, "title": "C", "tempo_bpm": 90.0}]}
    # Query is trimmed before delegating.
    assert rag.calls == [("hybrid", "calm", 80, 100, 4)]


@pytest.mark.asyncio
async def test_hybrid_search_empty_query_returns_empty():
    rag = FakeRag()
    result = await search_router.search_hybrid(
        HybridSearchRequest(query="   ", min_bpm=80, max_bpm=100), rag=rag
    )
    assert result == {"results": []}
    assert rag.calls == []


# --- SongRAGSystem.search_text_with_tempo (tempo filtering on text results) ---

def _make_rag_with_text_results(text_results):
    """Build a SongRAGSystem instance without running __init__ and stub the
    text-description search to return canned rows."""
    rag = SongRAGSystem.__new__(SongRAGSystem)

    async def fake_text(description, limit=10):
        return list(text_results)

    rag.search_by_text_description = fake_text  # type: ignore[assignment]
    return rag


@pytest.mark.asyncio
async def test_text_with_tempo_filters_to_band():
    rows = [
        {"id": 1, "title": "slow", "tempo_bpm": 70.0},
        {"id": 2, "title": "mid", "tempo_bpm": 95.0},
        {"id": 3, "title": "fast", "tempo_bpm": 150.0},
        {"id": 4, "title": "no-tempo", "tempo_bpm": None},
    ]
    rag = _make_rag_with_text_results(rows)
    results = await rag.search_text_with_tempo("calm", min_tempo=85, max_tempo=110)
    assert [r["id"] for r in results] == [2]


@pytest.mark.asyncio
async def test_text_with_tempo_invalid_band_returns_empty():
    rag = _make_rag_with_text_results([{"id": 1, "tempo_bpm": 100.0}])
    results = await rag.search_text_with_tempo("x", min_tempo=140, max_tempo=100)
    assert results == []


@pytest.mark.asyncio
async def test_text_with_tempo_no_band_returns_text_results():
    rows = [{"id": 1, "tempo_bpm": 70.0}, {"id": 2, "tempo_bpm": 150.0}]
    rag = _make_rag_with_text_results(rows)
    results = await rag.search_text_with_tempo("anything", limit=10)
    assert [r["id"] for r in results] == [1, 2]
