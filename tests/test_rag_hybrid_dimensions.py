"""
Assert-based tests for hybrid-search embedding dimensions (issue #27).

These exercise SongRAGSystem.search_hybrid's placeholder-vector behavior when one
embedding is missing, using an in-memory fake asyncpg pool that captures the bound
query args. No live database, no LLM, and no heavy embedding model is loaded — the
method only touches `self.db.pool`, so we bind it to a minimal stand-in instead of
constructing the full RAG system.
"""

import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.big_flavor_rag import (
    AUDIO_EMBEDDING_DIM,
    TEXT_EMBEDDING_DIM,
    SongRAGSystem,
)


class FakeConnection:
    """Captures the args bound to the hybrid-search query and returns no rows."""

    def __init__(self, captured):
        self._captured = captured

    async def fetch(self, query, *args):
        self._captured["query"] = " ".join(query.split())
        self._captured["args"] = args
        return []


class FakePool:
    def __init__(self, captured):
        self._captured = captured

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self._captured)


class FakeDB:
    def __init__(self, captured):
        self.pool = FakePool(captured)


def _make_rag(captured):
    """A minimal SongRAGSystem stand-in: search_hybrid only needs `self.db`."""
    rag = object.__new__(SongRAGSystem)
    rag.db = FakeDB(captured)
    return rag


def _parse_vector(arg: str) -> list:
    """search_hybrid passes vectors as their str(list) repr to pgvector."""
    return eval(arg)  # noqa: S307 — controlled, in-test repr of a float list


@pytest.mark.asyncio
async def test_missing_text_embedding_uses_384_placeholder():
    captured = {}
    rag = _make_rag(captured)

    results = await rag.search_hybrid(audio_embedding=[0.1] * AUDIO_EMBEDDING_DIM)

    assert results == []  # completes without a dimension error
    text_arg = captured["args"][1]
    assert len(_parse_vector(text_arg)) == TEXT_EMBEDDING_DIM == 384
    # Weights should flip entirely to audio when text is the missing one.
    assert captured["args"][2] == 1.0  # audio_weight
    assert captured["args"][3] == 0.0  # text_weight


@pytest.mark.asyncio
async def test_missing_audio_embedding_uses_549_placeholder():
    captured = {}
    rag = _make_rag(captured)

    results = await rag.search_hybrid(text_embedding=[0.1] * TEXT_EMBEDDING_DIM)

    assert results == []
    audio_arg = captured["args"][0]
    assert len(_parse_vector(audio_arg)) == AUDIO_EMBEDDING_DIM == 549
    assert captured["args"][2] == 0.0  # audio_weight
    assert captured["args"][3] == 1.0  # text_weight


@pytest.mark.asyncio
async def test_no_embeddings_raises():
    rag = _make_rag({})
    with pytest.raises(ValueError):
        await rag.search_hybrid()
