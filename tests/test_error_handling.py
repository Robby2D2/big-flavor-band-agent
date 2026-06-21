"""Tests for the centralized API error handling (src/api_errors.py).

These build a tiny throwaway FastAPI app wired with the same handlers the real
backend registers, so they exercise the error contract without touching the
database, the LLM, or the heavy agent/RAG imports.
"""
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api_errors import register_error_handlers  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    class Body(BaseModel):
        value: int

    @app.get("/boom")
    async def boom():
        raise ValueError("super secret internal detail /var/run/db")

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="Song not found")

    @app.post("/needs-body")
    async def needs_body(body: Body):
        return {"value": body.value}

    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_error_returns_generic_500(client):
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body == {"error": {"code": "internal_error", "message": "An internal error occurred."}}
    # The raw exception text must never reach the client.
    assert "super secret internal detail" not in resp.text
    assert "/var/run/db" not in resp.text


def test_explicit_404_uses_shared_body_shape(client):
    resp = client.get("/missing")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "Song not found"}}


def test_request_validation_returns_422_in_shared_shape(client):
    # Missing required field -> FastAPI RequestValidationError -> our 422 handler.
    resp = client.post("/needs-body", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "unprocessable_entity"
    # Validation internals (field locations, raw input) must not leak.
    assert "value" not in resp.text
