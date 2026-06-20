"""
Assert-based tests for the process-external radio state store (issue #2).

These use an in-memory fake asyncpg pool, so they exercise RadioStateStore's
serialization round-trip and the radio state mutators without a live database or
any LLM call.
"""

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.radio_state_store import RadioStateStore, default_state


class FakeConnection:
    """Minimal asyncpg-connection stand-in backed by a shared dict store."""

    def __init__(self, store):
        self._store = store

    async def execute(self, query: str, *args):
        q = " ".join(query.split())
        if q.startswith("INSERT INTO radio_state") and "DO NOTHING" in q:
            self._store.setdefault("state_row", json.loads(args[0]))
            return "INSERT 0 1"
        if q.startswith("INSERT INTO radio_state"):  # upsert (save_state)
            self._store["state_row"] = json.loads(args[0])
            return "INSERT 0 1"
        if q.startswith("INSERT INTO radio_listeners"):
            self._store["listeners"][args[0]] = True
            return "INSERT 0 1"
        if q.startswith("DELETE FROM radio_listeners"):
            # Tests drive cleanup explicitly; treat as "remove all stale" no-op.
            return "DELETE 0"
        raise AssertionError(f"unexpected execute query: {q}")

    async def fetchrow(self, query: str, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT state FROM radio_state"):
            row = self._store.get("state_row")
            return None if row is None else {"state": json.dumps(row)}
        if q.startswith("SELECT COUNT(*)"):
            return {"n": len(self._store["listeners"])}
        raise AssertionError(f"unexpected fetchrow query: {q}")


class FakePool:
    def __init__(self):
        self._store = {"state_row": None, "listeners": {}}

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self._store)


class FakeDB:
    def __init__(self):
        self.pool = FakePool()


@pytest.fixture
def store():
    return RadioStateStore(FakeDB())


@pytest.mark.asyncio
async def test_load_state_seeds_default_when_missing(store):
    state = await store.load_state()
    assert state["current_song"] is None
    assert state["queue"] == []
    assert state["is_playing"] is False


@pytest.mark.asyncio
async def test_save_then_load_round_trips_queue(store):
    state = default_state()
    state["queue"] = [{"id": 1, "title": "Song A"}, {"id": 2, "title": "Song B"}]
    state["current_song"] = {"id": 1, "title": "Song A"}
    state["is_playing"] = True
    await store.save_state(state)

    loaded = await store.load_state()
    assert loaded["current_song"] == {"id": 1, "title": "Song A"}
    assert [s["id"] for s in loaded["queue"]] == [1, 2]
    assert loaded["is_playing"] is True


@pytest.mark.asyncio
async def test_persisted_state_survives_a_fresh_store_instance(store):
    """A new RadioStateStore over the same DB sees the saved state (restart sim)."""
    state = default_state()
    state["queue"] = [{"id": 7, "title": "Persisted"}]
    await store.save_state(state)

    # Reuse the same underlying fake DB to simulate a process restart.
    restarted = RadioStateStore(store.db)
    loaded = await restarted.load_state()
    assert [s["id"] for s in loaded["queue"]] == [7]


@pytest.mark.asyncio
async def test_listener_register_and_count(store):
    assert await store.count_active_listeners() == 0
    await store.register_listener("listener-1")
    await store.register_listener("listener-2")
    await store.register_listener("listener-1")  # idempotent
    assert await store.count_active_listeners() == 2
