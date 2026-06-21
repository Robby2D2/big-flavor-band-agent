"""
Assert-based tests for the backend authorization dependency (src/auth.py).

Pure dependency logic — no DB, no LLM, no FastAPI app. The async dependency is
driven with asyncio.run so the suite needs only bare `pytest` (no pytest-asyncio).
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth import require_role  # noqa: E402

SECRET = "test-secret-value"


def _call(minimum_role, *, secret=None, role=None, env_secret=SECRET, monkeypatch=None):
    """Invoke the require_role dependency with the given headers/env and return its result."""
    if env_secret is None:
        monkeypatch.delenv("BACKEND_API_SECRET", raising=False)
    else:
        monkeypatch.setenv("BACKEND_API_SECRET", env_secret)
    dep = require_role(minimum_role)
    return asyncio.run(dep(x_service_secret=secret, x_user_role=role))


def test_valid_secret_and_sufficient_role_returns_role(monkeypatch):
    result = _call("editor", secret=SECRET, role="admin", monkeypatch=monkeypatch)
    assert result == "admin"


def test_exact_role_is_sufficient(monkeypatch):
    result = _call("editor", secret=SECRET, role="editor", monkeypatch=monkeypatch)
    assert result == "editor"


def test_missing_secret_is_401(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret=None, role="admin", monkeypatch=monkeypatch)
    assert exc.value.status_code == 401


def test_wrong_secret_is_401(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret="nope", role="admin", monkeypatch=monkeypatch)
    assert exc.value.status_code == 401


def test_insufficient_role_is_403(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("admin", secret=SECRET, role="editor", monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_listener_cannot_reach_editor_route(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret=SECRET, role="listener", monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_missing_role_header_is_403(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret=SECRET, role=None, monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_unknown_role_header_is_403(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret=SECRET, role="superuser", monkeypatch=monkeypatch)
    assert exc.value.status_code == 403


def test_fails_closed_when_secret_env_unset(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call("editor", secret=SECRET, role="admin", env_secret=None, monkeypatch=monkeypatch)
    assert exc.value.status_code == 401


def test_unknown_minimum_role_raises_value_error():
    with pytest.raises(ValueError):
        require_role("wizard")
