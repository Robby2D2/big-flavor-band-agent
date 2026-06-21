"""Shared FastAPI dependencies, long-lived singletons, and request/response models.

The ``agent``, ``rag``, and ``db_manager`` singletons are constructed exactly
once at startup by the FastAPI lifespan handler in ``backend_api.py`` (not lazily
per request), so the first request never pays cold-start and concurrent first
requests can't race an unlocked init. Every router depends on the accessors here
(``get_agent``/``get_rag``/``get_db``/``get_radio_store``) instead of
re-instantiating these per request.
"""
import logging
from typing import Optional, List, Dict, Any

from fastapi import HTTPException
from pydantic import BaseModel

from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager, RadioStateStore

logger = logging.getLogger("backend-api")

# Long-lived singletons shared across all routers. Assigned by the lifespan
# handler in backend_api.py at startup and cleared at shutdown.
agent: Optional[BigFlavorAgent] = None
rag: Optional[SongRAGSystem] = None
db_manager: Optional[DatabaseManager] = None

# Process-external radio state store (issue #2) — survives restarts and is shared
# across backend instances. Created lazily by get_radio_store on first use.
radio_store: Optional[RadioStateStore] = None

# Handle to the radio playback clock / queue top-up background task (issue #5),
# started by the lifespan handler.
radio_task = None


async def get_agent() -> BigFlavorAgent:
    """Dependency: return the agent initialized at startup."""
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    return agent


async def get_rag() -> SongRAGSystem:
    """Dependency: return the RAG system initialized at startup."""
    if rag is None:
        raise HTTPException(status_code=503, detail="RAG system not initialized")
    return rag


async def get_db() -> DatabaseManager:
    """Dependency: return the database manager initialized at startup."""
    if db_manager is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db_manager


async def get_radio_store() -> RadioStateStore:
    """Dependency to get or create the process-external radio state store."""
    global radio_store, db_manager
    if radio_store is None:
        if db_manager is None:
            db_manager = DatabaseManager()
            await db_manager.connect()
        radio_store = RadioStateStore(db_manager)
        await radio_store.ensure_initialized()
    return radio_store


# Request/Response Models
class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class AgentChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None


class SongRequest(BaseModel):
    song_title: Optional[str] = None
    song_id: Optional[int] = None


class AgentResponse(BaseModel):
    response: str
    songs: List[Dict[str, Any]] = []
    conversation_id: Optional[str] = None


class UserCreate(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None


class UpdateRoleRequest(BaseModel):
    user_id: str
    role: str


class AddToQueueRequest(BaseModel):
    message: str  # Natural language request for songs


class RemoveFromQueueRequest(BaseModel):
    song_id: int
