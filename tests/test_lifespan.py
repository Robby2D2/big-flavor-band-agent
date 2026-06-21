"""
Tests for the FastAPI app lifecycle (issue #4).

Verifies that the lifespan context manager constructs the agent / RAG / DB
singletons exactly once at startup (not lazily on first request) and closes the
DB pools on shutdown. Uses fakes — no live database and no live LLM.
"""
import pytest

import backend_api


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
    monkeypatch.setattr(backend_api, "DatabaseManager", FakeDatabaseManager)
    monkeypatch.setattr(backend_api, "SongRAGSystem", FakeRAG)
    monkeypatch.setattr(backend_api, "BigFlavorAgent", FakeAgent)
    monkeypatch.setattr(backend_api, "agent", None)
    monkeypatch.setattr(backend_api, "rag", None)
    monkeypatch.setattr(backend_api, "db_manager", None)
    yield


@pytest.mark.asyncio
async def test_lifespan_initializes_singletons_at_startup():
    assert backend_api.agent is None
    assert backend_api.rag is None
    assert backend_api.db_manager is None

    async with backend_api.lifespan(backend_api.app):
        # All three constructed before the app serves requests.
        assert isinstance(backend_api.agent, FakeAgent)
        assert isinstance(backend_api.rag, FakeRAG)
        assert isinstance(backend_api.db_manager, FakeDatabaseManager)
        assert backend_api.db_manager.connected is True
        assert backend_api.agent.initialized is True
        # RAG shares the backend's DB manager.
        assert backend_api.rag.db_manager is backend_api.db_manager


@pytest.mark.asyncio
async def test_lifespan_closes_pools_on_shutdown():
    async with backend_api.lifespan(backend_api.app):
        backend_db = backend_api.db_manager
        agent_db = backend_api.agent.db_manager

    # Both the backend's pool and the agent's own pool are closed on shutdown.
    assert backend_db.closed is True
    assert agent_db.closed is True
    assert backend_api.agent is None
    assert backend_api.rag is None
    assert backend_api.db_manager is None


@pytest.mark.asyncio
async def test_dependencies_return_startup_instances_without_reinit():
    async with backend_api.lifespan(backend_api.app):
        created = list(FakeDatabaseManager.instances)
        a = await backend_api.get_agent()
        r = await backend_api.get_rag()
        d = await backend_api.get_db()

        assert a is backend_api.agent
        assert r is backend_api.rag
        assert d is backend_api.db_manager
        # No dependency call constructed a new DatabaseManager (no lazy reinit).
        assert FakeDatabaseManager.instances == created


@pytest.mark.asyncio
async def test_dependencies_raise_503_before_startup():
    with pytest.raises(backend_api.HTTPException) as exc:
        await backend_api.get_agent()
    assert exc.value.status_code == 503
