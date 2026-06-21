"""Unit tests for DatabaseManager user/admin/lyrics methods (issue #8).

These exercise the typed data-access methods added so route handlers no longer
run inline SQL. They use a fake asyncpg pool — no live database, no LLM — so the
row->dict mapping and parameter passing can be asserted in isolation.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import DatabaseManager


class FakeConnection:
    """Records the SQL/args it was called with and returns a canned result."""

    def __init__(self, fetchrow_result=None, fetch_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetch_result = fetch_result if fetch_result is not None else []
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        return self._fetchrow_result

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self._fetch_result


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _Acquire(self._conn)


def make_manager(conn):
    db = DatabaseManager()
    db.pool = FakePool(conn)
    return db


@pytest.mark.asyncio
async def test_upsert_user_returns_row_as_dict_and_passes_params():
    row = {"id": "u1", "email": "a@b.com", "name": "Al", "picture": None,
           "role": "listener", "created_at": "t", "updated_at": "t"}
    conn = FakeConnection(fetchrow_result=row)
    db = make_manager(conn)

    result = await db.upsert_user("u1", "a@b.com", "Al", None)

    assert result == row
    assert isinstance(result, dict)
    query, args = conn.calls[0]
    assert "INSERT INTO users" in query
    assert "ON CONFLICT (id) DO UPDATE" in query
    assert args == ("u1", "a@b.com", "Al", None)


@pytest.mark.asyncio
async def test_upsert_user_returns_none_when_no_row():
    conn = FakeConnection(fetchrow_result=None)
    db = make_manager(conn)

    assert await db.upsert_user("u1", "a@b.com", "Al", None) is None


@pytest.mark.asyncio
async def test_get_user_role_returns_role_string():
    conn = FakeConnection(fetchrow_result={"role": "admin"})
    db = make_manager(conn)

    assert await db.get_user_role("u1") == "admin"
    query, args = conn.calls[0]
    assert args == ("u1",)


@pytest.mark.asyncio
async def test_get_user_role_returns_none_when_missing():
    conn = FakeConnection(fetchrow_result=None)
    db = make_manager(conn)

    assert await db.get_user_role("nope") is None


@pytest.mark.asyncio
async def test_list_users_maps_rows_to_dicts():
    rows = [{"id": "u1", "role": "admin"}, {"id": "u2", "role": "listener"}]
    conn = FakeConnection(fetch_result=rows)
    db = make_manager(conn)

    result = await db.list_users()

    assert result == rows
    assert all(isinstance(r, dict) for r in result)


@pytest.mark.asyncio
async def test_set_user_role_passes_role_then_user_id():
    row = {"id": "u1", "email": "a@b.com", "name": "Al", "role": "admin",
           "updated_at": "t"}
    conn = FakeConnection(fetchrow_result=row)
    db = make_manager(conn)

    result = await db.set_user_role("u1", "admin")

    assert result == row
    query, args = conn.calls[0]
    assert "UPDATE users" in query
    assert args == ("admin", "u1")


@pytest.mark.asyncio
async def test_set_user_role_returns_none_when_user_missing():
    conn = FakeConnection(fetchrow_result=None)
    db = make_manager(conn)

    assert await db.set_user_role("nope", "admin") is None


@pytest.mark.asyncio
async def test_get_song_lyrics_returns_content():
    conn = FakeConnection(fetchrow_result={"lyrics": "la la la"})
    db = make_manager(conn)

    assert await db.get_song_lyrics(42) == "la la la"
    query, args = conn.calls[0]
    assert "content_type = 'lyrics'" in query
    assert args == (42,)


@pytest.mark.asyncio
async def test_get_song_lyrics_returns_none_when_missing():
    conn = FakeConnection(fetchrow_result=None)
    db = make_manager(conn)

    assert await db.get_song_lyrics(999) is None
