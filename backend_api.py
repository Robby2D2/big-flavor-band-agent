"""
FastAPI backend server for BigFlavor Band Agent
Bridges the Next.js frontend with the Python agent
"""
import os
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import anthropic
from pathlib import Path

# Import our existing agent
from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager

app = FastAPI(title="BigFlavor Band Agent API", version="1.0.0")

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize agent and RAG system
agent: Optional[BigFlavorAgent] = None
rag: Optional[SongRAGSystem] = None
db_manager: Optional[DatabaseManager] = None


async def get_agent() -> BigFlavorAgent:
    """Dependency to get or create agent instance"""
    global agent
    if agent is None:
        agent = BigFlavorAgent()
        await agent.initialize()
    return agent


async def get_rag() -> SongRAGSystem:
    """Dependency to get or create RAG instance"""
    global rag, db_manager
    if rag is None:
        # Initialize database manager if needed
        if db_manager is None:
            db_manager = DatabaseManager()
            await db_manager.connect()
        # Create RAG system with database manager
        rag = SongRAGSystem(db_manager, use_clap=True)
    return rag


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


# Health check
@app.get("/")
async def root():
    return {
        "status": "ok",
        "service": "BigFlavor Band Agent API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# User management endpoints
class UserCreate(BaseModel):
    id: str
    email: str
    name: str
    picture: Optional[str] = None


@app.post("/api/users")
async def create_or_update_user(user: UserCreate):
    """Create or update a user in the database"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        # Insert or update user
        query = """
            INSERT INTO users (id, email, name, picture, role, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 'listener', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE
            SET email = EXCLUDED.email,
                name = EXCLUDED.name,
                picture = EXCLUDED.picture,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id, email, name, picture, role, created_at, updated_at
        """

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, user.id, user.email, user.name, user.picture)

        await db_manager.close()

        return {
            "id": result['id'],
            "email": result['email'],
            "name": result['name'],
            "picture": result['picture'],
            "role": result['role'],
            "created_at": result['created_at'].isoformat(),
            "updated_at": result['updated_at'].isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users/{user_id}/role")
async def get_user_role(user_id: str):
    """Get a user's role from the database"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        query = "SELECT role FROM users WHERE id = $1"

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, user_id)

        await db_manager.close()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        return {"role": result['role']}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Search endpoints
@app.post("/api/search/natural")
async def natural_language_search(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """
    Natural language search using the agent to interpret the query
    and use the appropriate tools
    """
    try:
        agent_instance = await get_agent()

        # Use the agent's search_songs method to get both text and song data
        result = await agent_instance.search_songs(request.query, request.limit)

        return {
            "query": request.query,
            "response": result["response"],
            "songs": result["songs"],
            "total_found": result["total_found"],
            "limit": request.limit
        }
    except Exception as e:
        import traceback
        print(f"ERROR in natural_language_search: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/text")
async def search_by_text(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by text description using semantic search"""
    try:
        results = await rag.search_by_text_description(
            description=request.query,
            limit=request.limit
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/lyrics")
async def search_by_lyrics(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by lyrics keywords"""
    try:
        results = await rag.search_lyrics_by_keyword(
            keyword=request.query,
            limit=request.limit
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Agent chat endpoints
@app.post("/api/agent/chat", response_model=AgentResponse)
async def chat_with_agent(
    request: AgentChatRequest,
    agent: BigFlavorAgent = Depends(get_agent)
):
    """
    Chat with the BigFlavor agent. The agent can search for songs,
    provide recommendations, and answer questions.
    """
    try:
        # Use search_songs to get both response and songs
        result = await agent.search_songs(request.message, limit=20)

        return AgentResponse(
            response=result["response"],
            songs=result["songs"],
            conversation_id=request.conversation_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/dj/request")
async def dj_song_request(
    request: SongRequest,
    agent: BigFlavorAgent = Depends(get_agent)
):
    """
    Request a song from the DJ. The agent will find and queue the song.
    """
    try:
        if request.song_title:
            message = f"Please play '{request.song_title}'"
        elif request.song_id:
            message = f"Please play song ID {request.song_id}"
        else:
            raise HTTPException(status_code=400, detail="Either song_title or song_id required")

        response = await agent.process_message(message)

        return {
            "response": response,
            "status": "queued"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agent/dj/playlist")
async def dj_create_playlist(
    request: AgentChatRequest,
    agent: BigFlavorAgent = Depends(get_agent)
):
    """
    Ask the DJ agent to create a playlist based on criteria
    """
    try:
        prompt = f"""You are a DJ for BigFlavor Band. Create a playlist based on this request:

"{request.message}"

Use your search tools to find appropriate songs and create a cohesive playlist.
Explain your selections and the vibe you're creating."""

        response = await agent.process_message(prompt)

        return {
            "response": response
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Audio streaming endpoint
@app.get("/api/audio/stream/{song_id}")
async def stream_audio(song_id: int):
    """
    Stream audio file for a song
    """
    try:
        # Get song info from database to find audio path
        from src.rag.big_flavor_rag import SongRAGSystem
        rag = SongRAGSystem()

        # Find the audio file
        audio_library = Path("audio_library")

        # Look for file matching the song ID pattern
        audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))

        if not audio_files:
            raise HTTPException(status_code=404, detail=f"Audio file for song {song_id} not found")

        audio_path = audio_files[0]

        def iterfile():
            with open(audio_path, mode="rb") as file_like:
                yield from file_like

        return StreamingResponse(
            iterfile(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"inline; filename={audio_path.name}",
                "Accept-Ranges": "bytes"
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# MCP Tools endpoints (for editors)
@app.get("/api/tools/list")
async def list_tools(agent: BigFlavorAgent = Depends(get_agent)):
    """List all available MCP tools"""
    try:
        tools = agent.get_available_tools()
        return {"tools": tools}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tools/execute")
async def execute_tool(
    tool_name: str,
    parameters: Dict[str, Any],
    agent: BigFlavorAgent = Depends(get_agent)
):
    """Execute an MCP tool (editors only)"""
    try:
        result = await agent.execute_tool(tool_name, parameters)
        return {"result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
