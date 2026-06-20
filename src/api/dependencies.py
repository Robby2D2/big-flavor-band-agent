"""Shared FastAPI dependencies and request/response models.

Holds the long-lived singletons (`agent`, `rag`, `db_manager`) initialised
lazily and shared by every router, so no router re-instantiates them per
request. Also defines the Pydantic models used across the routers.
"""
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager

# Long-lived singletons shared across all routers.
agent: Optional[BigFlavorAgent] = None
rag: Optional[SongRAGSystem] = None
db_manager: Optional[DatabaseManager] = None


async def get_agent() -> BigFlavorAgent:
    """Dependency to get or create the agent instance."""
    global agent
    if agent is None:
        agent = BigFlavorAgent()
        await agent.initialize()
    return agent


async def get_rag() -> SongRAGSystem:
    """Dependency to get or create the RAG instance."""
    global rag, db_manager
    if rag is None:
        if db_manager is None:
            db_manager = DatabaseManager()
            await db_manager.connect()
        rag = SongRAGSystem(db_manager, use_clap=True)
    return rag


async def get_db() -> DatabaseManager:
    """Dependency to get or create the database manager instance."""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
        await db_manager.connect()
    return db_manager


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
