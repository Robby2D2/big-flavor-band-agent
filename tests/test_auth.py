"""
Assert-based tests for the backend authorization dependency (src/auth.py).

Pure dependency logic — no DB, no LLM, no FastAPI app. The async dependency is
driven with asyncio.run so the suite needs only bare `pytest` (no pytest-asyncio).

``require_caller`` and ``optional_caller`` (issue #102) carry the caller's identity as
well as their rank, for routes that cannot decide on rank alone. The property worth
pinning there is that identity is believed **only** behind the service secret: without
it, anyone on the Docker network could claim to be another user (ACCT-03).
"""
import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth import (  # noqa: E402
    optional_caller,
    require_caller,
    require_role,
    role_at_least,
)

SECRET = "test-secret-value"


def _call(minimum_role, *, secret=None, role=None, env_secret=SECRET, monkeypatch=None):
    """Invoke the require_role dependency with the given headers/env and return its result."""
    if env_secret is None:
        monkeypatch.delenv("BACKEND_API_SECRET", raising=False)
    else:
        monkeypatch.setenv("BACKEND_API_SECRET", env_secret)
    dep = require_role(minimum_role)
    return asyncio.run(dep(x_service_secret=secret, x_user_role=role))


def _call_caller(minimum_role, *, secret=None, role=None, user_id=None, monkeypatch=None):
    """Invoke the require_caller dependency and return the Caller it resolved."""
    monkeypatch.setenv("BACKEND_API_SECRET", SECRET)
    dep = require_caller(minimum_role)
    return asyncio.run(
        dep(x_service_secret=secret, x_user_role=role, x_user_id=user_id)
    )


def _call_optional(*, secret=None, role=None, user_id=None, env_secret=SECRET, monkeypatch=None):
    """Invoke the optional_caller dependency and return the Caller it resolved."""
    if env_secret is None:
        monkeypatch.delenv("BACKEND_API_SECRET", raising=False)
    else:
        monkeypatch.setenv("BACKEND_API_SECRET", env_secret)
    return asyncio.run(
        optional_caller(x_service_secret=secret, x_user_role=role, x_user_id=user_id)
    )


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


def test_unknown_minimum_caller_role_raises_value_error():
    with pytest.raises(ValueError):
        require_caller("wizard")


# --- role_at_least --------------------------------------------------------

def test_role_at_least_ranks_the_hierarchy():
    assert role_at_least("admin", "editor")
    assert role_at_least("editor", "editor")
    assert not role_at_least("listener", "editor")


def test_role_at_least_refuses_an_unknown_or_missing_role():
    assert not role_at_least(None, "listener")
    assert not role_at_least("wizard", "listener")


# --- require_caller: rank *and* identity ----------------------------------

def test_require_caller_returns_role_and_user_id(monkeypatch):
    caller = _call_caller(
        "listener", secret=SECRET, role="editor", user_id="sub-123", monkeypatch=monkeypatch
    )
    assert caller.role == "editor"
    assert caller.user_id == "sub-123"


def test_require_caller_still_enforces_the_secret(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call_caller(
            "listener", secret="nope", role="editor", user_id="sub-123", monkeypatch=monkeypatch
        )
    assert exc.value.status_code == 401


def test_require_caller_still_enforces_the_minimum_role(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call_caller(
            "editor", secret=SECRET, role="listener", user_id="sub-123", monkeypatch=monkeypatch
        )
    assert exc.value.status_code == 403


def test_require_caller_reports_a_missing_user_id_as_none(monkeypatch):
    # A caller whose identity is unknown must be distinguishable from one who is
    # known, so a route can refuse rather than match on a blank (ACCT-04).
    caller = _call_caller(
        "listener", secret=SECRET, role="listener", user_id=None, monkeypatch=monkeypatch
    )
    assert caller.user_id is None


def test_require_caller_treats_an_empty_user_id_as_none(monkeypatch):
    caller = _call_caller(
        "listener", secret=SECRET, role="listener", user_id="", monkeypatch=monkeypatch
    )
    assert caller.user_id is None


# --- optional_caller: open to all, believed only behind the secret --------

def test_optional_caller_reads_identity_when_the_secret_is_valid(monkeypatch):
    caller = _call_optional(
        secret=SECRET, role="listener", user_id="sub-123", monkeypatch=monkeypatch
    )
    assert caller.role == "listener"
    assert caller.user_id == "sub-123"


def test_optional_caller_ignores_identity_without_the_secret(monkeypatch):
    # The point of the whole dependency: an unverified caller may still reach an open
    # route, but their claim about who they are counts for nothing (ACCT-03).
    caller = _call_optional(secret=None, role="admin", user_id="sub-123", monkeypatch=monkeypatch)
    assert caller.role is None
    assert caller.user_id is None


def test_optional_caller_ignores_identity_with_a_wrong_secret(monkeypatch):
    caller = _call_optional(secret="nope", role="admin", user_id="sub-123", monkeypatch=monkeypatch)
    assert caller == (None, None)


def test_optional_caller_ignores_identity_when_the_secret_env_is_unset(monkeypatch):
    caller = _call_optional(
        secret=SECRET, role="admin", user_id="sub-123", env_secret=None, monkeypatch=monkeypatch
    )
    assert caller == (None, None)


def test_optional_caller_does_not_raise_for_an_anonymous_caller(monkeypatch):
    # Unlike require_*, being unidentified is allowed here — it just is not trusted.
    caller = _call_optional(monkeypatch=monkeypatch)
    assert caller == (None, None)
