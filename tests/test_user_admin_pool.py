"""
Tests that the user/admin endpoints reuse the shared application connection pool
(injected via Depends(get_db)) instead of constructing/closing a DatabaseManager
per request.

No live database or LLM is touched: get_db is overridden with a fake whose
pool.acquire() yields a fake connection returning canned rows.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import backend_api
from backend_api import app, get_db


class FakeConnection:
    """Minimal asyncpg-connection stand-in returning preconfigured rows."""

    def __init__(self, fetchrow_result=None, fetch_result=None):
        self._fetchrow_result = fetchrow_result
        self._fetch_result = fetch_result

    async def fetchrow(self, query, *args):
        return self._fetchrow_result

    async def fetch(self, query, *args):
        return self._fetch_result or []


class FakeAcquire:
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
        return FakeAcquire(self._conn)


class FakeDatabaseManager:
    """Stand-in for the shared singleton. connect()/close() must NOT be called
    by the request handlers."""

    def __init__(self, conn):
        self.pool = FakePool(conn)
        self.connect_called = False
        self.close_called = False

    async def connect(self):
        self.connect_called = True

    async def close(self):
        self.close_called = True


def _override_db(fake):
    async def _dep():
        return fake

    return _dep


def _no_real_pool_constructed(monkeypatch):
    """Fail loudly if any handler tries to build its own DatabaseManager/pool."""

    def _boom(*args, **kwargs):
        raise AssertionError("handler constructed its own DatabaseManager")

    monkeypatch.setattr(backend_api, "DatabaseManager", _boom)


def test_create_or_update_user_uses_shared_pool(monkeypatch):
    now = datetime(2026, 6, 20, 12, 0, 0)
    row = {
        "id": "u1", "email": "a@b.com", "name": "A", "picture": None,
        "role": "listener", "created_at": now, "updated_at": now,
    }
    fake = FakeDatabaseManager(FakeConnection(fetchrow_result=row))
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.post("/api/users", json={
            "id": "u1", "email": "a@b.com", "name": "A",
        })
        assert resp.status_code == 200
        assert resp.json()["id"] == "u1"
        assert resp.json()["role"] == "listener"
        assert not fake.connect_called
        assert not fake.close_called
    finally:
        app.dependency_overrides.clear()


def test_get_user_role_uses_shared_pool(monkeypatch):
    fake = FakeDatabaseManager(FakeConnection(fetchrow_result={"role": "admin"}))
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.get("/api/users/u1/role")
        assert resp.status_code == 200
        assert resp.json() == {"role": "admin"}
        assert not fake.connect_called
        assert not fake.close_called
    finally:
        app.dependency_overrides.clear()


def test_get_user_role_not_found_returns_404(monkeypatch):
    fake = FakeDatabaseManager(FakeConnection(fetchrow_result=None))
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.get("/api/users/missing/role")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_all_users_uses_shared_pool(monkeypatch):
    now = datetime(2026, 6, 20, 12, 0, 0)
    rows = [{
        "id": "u1", "email": "a@b.com", "name": "A", "picture": None,
        "role": "listener", "created_at": now, "updated_at": now,
    }]
    fake = FakeDatabaseManager(FakeConnection(fetch_result=rows))
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.get("/api/admin/users")
        assert resp.status_code == 200
        assert resp.json()["users"][0]["id"] == "u1"
        assert not fake.connect_called
        assert not fake.close_called
    finally:
        app.dependency_overrides.clear()


def test_update_user_role_uses_shared_pool(monkeypatch):
    now = datetime(2026, 6, 20, 12, 0, 0)
    row = {
        "id": "u1", "email": "a@b.com", "name": "A",
        "role": "editor", "updated_at": now,
    }
    fake = FakeDatabaseManager(FakeConnection(fetchrow_result=row))
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.put("/api/admin/users/role", json={
            "user_id": "u1", "role": "editor",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"
        assert not fake.connect_called
        assert not fake.close_called
    finally:
        app.dependency_overrides.clear()


def test_update_user_role_rejects_invalid_role(monkeypatch):
    fake = FakeDatabaseManager(FakeConnection())
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.put("/api/admin/users/role", json={
            "user_id": "u1", "role": "superuser",
        })
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
