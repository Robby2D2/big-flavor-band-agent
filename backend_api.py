"""
FastAPI backend server for BigFlavor Band Agent
Bridges the Next.js frontend with the Python agent
"""
import os
import asyncio
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
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

# Radio station state
import time
from datetime import datetime
import uuid

radio_state = {
    "queue": [],  # List of song objects - Liquidsoap handles actual playback
}

# Playlist file path for Liquidsoap integration
PLAYLIST_FILE = Path("/app/streaming/playlist/radio.m3u")

def write_playlist_file():
    """Write current queue to playlist file for Liquidsoap"""
    try:
        audio_library = Path("/app/audio_library")
        playlist_lines = ["#EXTM3U"]

        # Add all songs from queue
        for song in radio_state["queue"]:
            song_id = song.get("id")
            title = song.get("title", "Unknown")
            audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))
            if audio_files:
                playlist_lines.append(f"#EXTINF:-1,{title}")
                # Convert path for Liquidsoap container: /app/audio_library -> /audio_library
                liquidsoap_path = str(audio_files[0]).replace("/app/audio_library", "/audio_library")
                playlist_lines.append(liquidsoap_path)

        # Write playlist file
        PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        PLAYLIST_FILE.write_text("\n".join(playlist_lines))
        print(f"Playlist updated with {len(radio_state['queue'])} songs")
    except Exception as e:
        print(f"Error writing playlist: {e}")

# Track active listeners (listener_id -> last_ping_time)
active_listeners = {}


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


async def get_db() -> DatabaseManager:
    """Dependency to get or create database manager instance"""
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


# Admin endpoints
@app.get("/api/admin/users")
async def get_all_users():
    """Get all users (admin only)"""
    try:
        db_manager = DatabaseManager()
        await db_manager.connect()

        query = """
            SELECT id, email, name, picture, role, created_at, updated_at
            FROM users
            ORDER BY created_at DESC
        """

        async with db_manager.pool.acquire() as conn:
            results = await conn.fetch(query)

        await db_manager.close()

        users = [
            {
                "id": row['id'],
                "email": row['email'],
                "name": row['name'],
                "picture": row['picture'],
                "role": row['role'],
                "created_at": row['created_at'].isoformat(),
                "updated_at": row['updated_at'].isoformat()
            }
            for row in results
        ]

        return {"users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateRoleRequest(BaseModel):
    user_id: str
    role: str


@app.put("/api/admin/users/role")
async def update_user_role(request: UpdateRoleRequest):
    """Update a user's role (admin only)"""
    try:
        # Validate role
        valid_roles = ['listener', 'editor', 'admin']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        db_manager = DatabaseManager()
        await db_manager.connect()

        query = """
            UPDATE users
            SET role = $1, updated_at = CURRENT_TIMESTAMP
            WHERE id = $2
            RETURNING id, email, name, role, updated_at
        """

        async with db_manager.pool.acquire() as conn:
            result = await conn.fetchrow(query, request.role, request.user_id)

        await db_manager.close()

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        return {
            "id": result['id'],
            "email": result['email'],
            "name": result['name'],
            "role": result['role'],
            "updated_at": result['updated_at'].isoformat()
        }
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
            "search_summary": result.get("search_summary"),
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


@app.get("/api/songs/{song_id}/lyrics")
async def get_song_lyrics(
    song_id: int,
    db: DatabaseManager = Depends(get_db)
):
    """Get lyrics for a specific song"""
    try:
        query = """
            SELECT content as lyrics
            FROM text_embeddings
            WHERE song_id = $1 AND content_type = 'lyrics'
        """
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)

        if row:
            return {"lyrics": row["lyrics"]}
        else:
            return {"lyrics": "Lyrics not available for this song."}
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


# Radio Station endpoints


async def auto_populate_queue():
    """Auto-populate queue with songs if it's running low"""
    global radio_state

    if len(radio_state["queue"]) < 5:
        try:
            # Use the agent to find good songs
            agent_instance = await get_agent()
            result = await agent_instance.search_songs("Find me some great songs to keep the vibe going", limit=10)

            # Add songs to queue
            for song in result["songs"]:
                if song not in radio_state["queue"]:
                    # Normalize field names: duration_seconds -> duration
                    if "duration_seconds" in song and "duration" not in song:
                        song["duration"] = song["duration_seconds"]
                    radio_state["queue"].append(song)
        except Exception as e:
            print(f"Error auto-populating queue: {e}")


def cleanup_stale_listeners():
    """Remove listeners that haven't pinged in 10+ seconds"""
    global active_listeners
    current_time = time.time()
    stale_threshold = 10  # seconds

    stale_listeners = [
        listener_id for listener_id, last_ping in active_listeners.items()
        if current_time - last_ping > stale_threshold
    ]

    for listener_id in stale_listeners:
        del active_listeners[listener_id]


def register_listener(listener_id: str):
    """Register a listener as active"""
    global active_listeners
    active_listeners[listener_id] = time.time()


@app.get("/api/radio/state")
async def get_radio_state(listener_id: str = None):
    """Get current radio state (queue management only - Liquidsoap handles playback)"""
    try:
        # Clean up stale listeners
        cleanup_stale_listeners()

        # Generate listener ID if not provided
        if not listener_id:
            listener_id = str(uuid.uuid4())

        # Register this listener
        register_listener(listener_id)

        # Auto-populate queue if needed
        await auto_populate_queue()

        # Get first song as "current" for display purposes
        current_song = radio_state["queue"][0] if len(radio_state["queue"]) > 0 else None

        return {
            "current_song": current_song,  # First song in queue for display
            "queue": radio_state["queue"],  # All songs in queue
            "is_playing": len(radio_state["queue"]) > 0,
            "queue_length": len(radio_state["queue"]),
            "listener_id": listener_id,
            "active_listeners": len(active_listeners)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AddToQueueRequest(BaseModel):
    message: Optional[str] = None  # Natural language request for songs
    song_id: Optional[int] = None  # Specific song ID to add


@app.post("/api/radio/queue/add")
async def add_to_queue(
    request: AddToQueueRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db)
):
    """Add songs to queue via DJ agent (all authenticated users)"""
    try:
        added_count = 0
        response_text = ""

        # If song_id is provided, add that specific song
        if request.song_id:
            # Fetch song from database
            query = """
                SELECT id, title, genre, tempo_bpm, key, duration_seconds,
                       mood, energy, recording_date
                FROM songs
                WHERE id = $1
            """
            async with db.pool.acquire() as conn:
                row = await conn.fetchrow(query, request.song_id)

            if not row:
                raise HTTPException(status_code=404, detail=f"Song ID {request.song_id} not found")

            # Convert database row to song dict
            song = {
                "id": row["id"],
                "title": row["title"],
                "genre": row["genre"],
                "tempo_bpm": row["tempo_bpm"],
                "key": row["key"],
                "duration": row["duration_seconds"],
                "duration_seconds": row["duration_seconds"],
                "mood": row["mood"],
                "energy": row["energy"],
                "recording_date": row["recording_date"].isoformat() if row["recording_date"] else None,
            }

            # Check if song not already in queue
            if not any(s.get("id") == song["id"] for s in radio_state["queue"]):
                radio_state["queue"].append(song)
                added_count = 1
                response_text = f"Added '{song['title']}' to the queue"
            else:
                response_text = f"'{song['title']}' is already in the queue"

        # Otherwise, use agent to find songs by message
        elif request.message:
            # Use agent to find songs
            result = await agent.search_songs(request.message, limit=20)

            # Add to queue
            for song in result["songs"]:
                # Check if song not already in queue
                if not any(s.get("id") == song.get("id") for s in radio_state["queue"]):
                    # Normalize field names: duration_seconds -> duration
                    if "duration_seconds" in song and "duration" not in song:
                        song["duration"] = song["duration_seconds"]
                    radio_state["queue"].append(song)
                    added_count += 1

            response_text = result["response"]
        else:
            raise HTTPException(status_code=400, detail="Either message or song_id is required")

        # Update playlist file if songs were added
        if added_count > 0:
            write_playlist_file()

        return {
            "response": response_text,
            "added_count": added_count,
            "queue_length": len(radio_state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/radio/skip")
async def skip_song():
    """Skip to next song (editor/admin only) - removes first song from queue"""
    try:
        if len(radio_state["queue"]) > 0:
            skipped = radio_state["queue"].pop(0)
            print(f"Skipped: {skipped.get('title')}")
            write_playlist_file()

        # Auto-populate if needed
        await auto_populate_queue()

        current_song = radio_state["queue"][0] if len(radio_state["queue"]) > 0 else None

        return {
            "current_song": current_song,
            "queue_length": len(radio_state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RemoveFromQueueRequest(BaseModel):
    song_id: int


@app.post("/api/radio/queue/remove")
async def remove_from_queue(request: RemoveFromQueueRequest):
    """Remove a song from the queue (editor/admin only)"""
    try:
        # Find and remove the song
        original_length = len(radio_state["queue"])
        radio_state["queue"] = [s for s in radio_state["queue"] if s.get("id") != request.song_id]

        removed = original_length - len(radio_state["queue"])

        return {
            "removed": removed > 0,
            "queue_length": len(radio_state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# Radio Stream endpoint (HLS playlist)
@app.get("/stream")
async def radio_stream(request: Request):
    """
    Returns an HLS playlist for the radio stream.
    Can be used with any HLS-compatible player (VLC, browsers with hls.js, etc.)
    """
    try:
        # Auto-populate queue if needed
        await auto_populate_queue()

        # Build base URL from request
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Build HLS playlist
        playlist_lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:600",  # Max segment duration (10 minutes)
            "#EXT-X-MEDIA-SEQUENCE:0",
        ]

        # Add all songs from queue
        for song in radio_state["queue"][:10]:  # Next 10 songs
            duration = song.get("duration", song.get("duration_seconds", 180))
            title = song.get("title", "Unknown")
            song_id = song.get("id")

            playlist_lines.append(f"#EXTINF:{duration},{title}")
            playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

        playlist_content = "\n".join(playlist_lines)

        return Response(
            content=playlist_content,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Content-Disposition": "inline; filename=bigflavor-radio.m3u8",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stream.m3u")
async def radio_stream_m3u(request: Request):
    """
    Returns a simple M3U playlist for the radio stream.
    Compatible with most media players (VLC, Winamp, etc.)
    """
    try:
        # Auto-populate queue if needed
        await auto_populate_queue()

        # Build base URL from request
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Build M3U playlist
        playlist_lines = ["#EXTM3U"]

        # Add all songs from queue
        for song in radio_state["queue"][:10]:
            duration = int(song.get("duration", song.get("duration_seconds", 180)))
            title = song.get("title", "Unknown")
            song_id = song.get("id")

            playlist_lines.append(f"#EXTINF:{duration},{title}")
            playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

        playlist_content = "\n".join(playlist_lines)

        return Response(
            content=playlist_content,
            media_type="audio/x-mpegurl",
            headers={
                "Content-Disposition": "inline; filename=bigflavor-radio.m3u",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Audio streaming endpoint
@app.get("/api/audio/stream/{song_id}")
async def stream_audio(song_id: int):
    """
    Stream audio file for a song
    """
    try:
        # Find the audio file directly (don't create RAG system - too expensive)
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
