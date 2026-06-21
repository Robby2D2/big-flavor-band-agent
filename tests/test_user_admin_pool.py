"""
Tests that the user/admin endpoints reuse the shared application connection pool
(injected via Depends(get_db)) instead of constructing/closing a DatabaseManager
per request.

No live database or LLM is touched: get_db is overridden with a fake whose
DatabaseManager methods return canned rows. The handlers reach the data layer
through those methods (issue #8) on the shared injected singleton (issue #3),
so the fake must never have connect()/close() called on it.
"""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import backend_api
from backend_api import app, get_db


class FakeDatabaseManager:
    """Stand-in for the shared singleton. Exposes the DatabaseManager data
    methods the handlers call; connect()/close() must NOT be called by the
    request handlers (they reuse the already-connected shared pool)."""

    def __init__(self, upsert_user=None, get_user_role=None,
                 list_users=None, set_user_role=None):
        self._upsert_user = upsert_user
        self._get_user_role = get_user_role
        self._list_users = list_users if list_users is not None else []
        self._set_user_role = set_user_role
        self.connect_called = False
        self.close_called = False

    async def connect(self):
        self.connect_called = True

    async def close(self):
        self.close_called = True

    async def upsert_user(self, *args, **kwargs):
        return self._upsert_user

    async def get_user_role(self, *args, **kwargs):
        return self._get_user_role

    async def list_users(self, *args, **kwargs):
        return self._list_users

    async def set_user_role(self, *args, **kwargs):
        return self._set_user_role


def _override_db(fake):
    async def _dep():
        return fake

    return _dep


def _no_real_pool_constructed(monkeypatch):
    """Fail loudly if any handler tries to build its own DatabaseManager/pool."""

    def _boom(*args, **kwargs):
        raise AssertionError("handler constructed its own DatabaseManager")

    monkeypatch.setattr(backend_api, "DatabaseManager", _boom)


# Admin endpoints are protected by require_role("admin") (issue #1): configure the
# service secret and present the BFF's trusted headers so the authz gate passes and
# we actually exercise the shared-pool path behind it.
_ADMIN_SECRET = "test-secret-value"


def _admin_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _ADMIN_SECRET)
    return {"X-Service-Secret": _ADMIN_SECRET, "X-User-Role": "admin"}


def test_create_or_update_user_uses_shared_pool(monkeypatch):
    now = datetime(2026, 6, 20, 12, 0, 0)
    row = {
        "id": "u1", "email": "a@b.com", "name": "A", "picture": None,
        "role": "listener", "created_at": now, "updated_at": now,
    }
    fake = FakeDatabaseManager(upsert_user=row)
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
    fake = FakeDatabaseManager(get_user_role="admin")
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
    fake = FakeDatabaseManager(get_user_role=None)
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
    fake = FakeDatabaseManager(list_users=rows)
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.get("/api/admin/users", headers=_admin_headers(monkeypatch))
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
    fake = FakeDatabaseManager(set_user_role=row)
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.put("/api/admin/users/role", json={
            "user_id": "u1", "role": "editor",
        }, headers=_admin_headers(monkeypatch))
        assert resp.status_code == 200
        assert resp.json()["role"] == "editor"
        assert not fake.connect_called
        assert not fake.close_called
    finally:
        app.dependency_overrides.clear()


def test_update_user_role_rejects_invalid_role(monkeypatch):
    fake = FakeDatabaseManager()
    _no_real_pool_constructed(monkeypatch)
    app.dependency_overrides[get_db] = _override_db(fake)
    try:
        client = TestClient(app)
        resp = client.put("/api/admin/users/role", json={
            "user_id": "u1", "role": "superuser",
        }, headers=_admin_headers(monkeypatch))
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.clear()
