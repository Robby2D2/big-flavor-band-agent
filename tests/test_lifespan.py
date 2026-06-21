"""
Tests for the FastAPI app lifecycle (issue #4).

Verifies that the lifespan context manager constructs the agent / RAG / DB
singletons exactly once at startup (not lazily on first request) and closes the
DB pools on shutdown. Uses fakes — no live database and no live LLM.

After the router split (issue #7) the lifespan lives in ``backend_api`` but the
singletons it manages live in ``src.api.dependencies`` (where every router's
get_* accessor reads them), so the assertions target that module.
"""
import pytest
from fastapi import HTTPException

import backend_api
from src.api import dependencies as deps


class FakeDatabaseManager:
    instances = []

    def __init__(self):
        self.connected = False
        self.closed = False
        FakeDatabaseManager.instances.append(self)

    async def connect(self):
        self.connected = True

    async def close(self):
        self.closed = True


class FakeRAG:
    def __init__(self, db_manager, use_clap=True):
        self.db_manager = db_manager
        self.use_clap = use_clap


class FakeAgent:
    def __init__(self):
        # The real agent constructs its own DatabaseManager in initialize();
        # mirror that so shutdown can close it.
        self.db_manager = FakeDatabaseManager()
        self.initialized = False

    async def initialize(self):
        await self.db_manager.connect()
        self.initialized = True


@pytest.fixture(autouse=True)
def patch_singletons(monkeypatch):
    FakeDatabaseManager.instances = []
    # The lifespan constructs these by name out of the backend_api module.
    monkeypatch.setattr(backend_api, "DatabaseManager", FakeDatabaseManager)
    monkeypatch.setattr(backend_api, "SongRAGSystem", FakeRAG)
    monkeypatch.setattr(backend_api, "BigFlavorAgent", FakeAgent)
    # The singletons themselves live in src.api.dependencies.
    monkeypatch.setattr(deps, "agent", None)
    monkeypatch.setattr(deps, "rag", None)
    monkeypatch.setattr(deps, "db_manager", None)
    monkeypatch.setattr(deps, "radio_task", None)
    # Don't spin up the real radio background loop in these unit tests.
    async def _noop_loop():
        return None
    monkeypatch.setattr(backend_api, "radio_background_loop", _noop_loop)
    yield


@pytest.mark.asyncio
async def test_lifespan_initializes_singletons_at_startup():
    assert deps.agent is None
    assert deps.rag is None
    assert deps.db_manager is None

    async with backend_api.lifespan(backend_api.app):
        # All three constructed before the app serves requests.
        assert isinstance(deps.agent, FakeAgent)
        assert isinstance(deps.rag, FakeRAG)
        assert isinstance(deps.db_manager, FakeDatabaseManager)
        assert deps.db_manager.connected is True
        assert deps.agent.initialized is True
        # RAG shares the backend's DB manager.
        assert deps.rag.db_manager is deps.db_manager


@pytest.mark.asyncio
async def test_lifespan_closes_pools_on_shutdown():
    async with backend_api.lifespan(backend_api.app):
        backend_db = deps.db_manager
        agent_db = deps.agent.db_manager

    # Both the backend's pool and the agent's own pool are closed on shutdown.
    assert backend_db.closed is True
    assert agent_db.closed is True
    assert deps.agent is None
    assert deps.rag is None
    assert deps.db_manager is None


@pytest.mark.asyncio
async def test_dependencies_return_startup_instances_without_reinit():
    async with backend_api.lifespan(backend_api.app):
        created = list(FakeDatabaseManager.instances)
        a = await backend_api.get_agent()
        r = await backend_api.get_rag()
        d = await backend_api.get_db()

        assert a is deps.agent
        assert r is deps.rag
        assert d is deps.db_manager
        # No dependency call constructed a new DatabaseManager (no lazy reinit).
        assert FakeDatabaseManager.instances == created


@pytest.mark.asyncio
async def test_dependencies_raise_503_before_startup():
    with pytest.raises(HTTPException) as exc:
        await backend_api.get_agent()
    assert exc.value.status_code == 503
