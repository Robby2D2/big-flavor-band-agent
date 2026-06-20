"""Tests for DatabaseManager's DB password resolution policy (issue #11).

Covers the fail-fast behavior when DB_PASSWORD is unset outside an explicit dev
context, and that the dev default / explicit overrides still work. No real DB
connection is made.
"""

import os
import sys

import pytest

# Make the repo root importable so `database.database` resolves regardless of cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.database import (  # noqa: E402
    DatabaseManager,
    _DEV_PASSWORD_DEFAULT,
    _resolve_db_password,
)


@pytest.fixture(autouse=True)
def _clean_db_env(monkeypatch):
    """Start each test from a known env state."""
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    yield


def test_dev_env_uses_dev_default_when_password_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert _resolve_db_password() == _DEV_PASSWORD_DEFAULT


def test_dev_short_alias_uses_dev_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    assert _resolve_db_password() == _DEV_PASSWORD_DEFAULT


def test_non_dev_env_fails_fast_when_password_unset(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="DB_PASSWORD is not set"):
        _resolve_db_password()


def test_default_env_is_treated_as_non_dev(monkeypatch):
    # APP_ENV unset -> fail closed, do not silently use the dev default.
    with pytest.raises(RuntimeError, match="DB_PASSWORD is not set"):
        _resolve_db_password()


def test_env_password_is_used_in_non_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_PASSWORD", "real_secret")
    assert _resolve_db_password() == "real_secret"


def test_env_password_overrides_dev_default(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DB_PASSWORD", "real_secret")
    assert _resolve_db_password() == "real_secret"


def test_manager_honors_explicit_password_arg_in_non_dev(monkeypatch):
    # An explicitly passed password must always win and never trigger fail-fast.
    monkeypatch.setenv("APP_ENV", "production")
    manager = DatabaseManager(password="explicit_pw")
    assert manager.password == "explicit_pw"


def test_manager_fails_fast_in_non_dev_without_password(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="DB_PASSWORD is not set"):
        DatabaseManager()


def test_manager_uses_dev_default_in_dev(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    manager = DatabaseManager()
    assert manager.password == _DEV_PASSWORD_DEFAULT
