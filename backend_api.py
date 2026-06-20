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
from database import DatabaseManager, RadioStateStore

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
radio_store: Optional[RadioStateStore] = None

# Radio station state
import time
from datetime import datetime
import uuid

# Playlist file path for Liquidsoap integration
PLAYLIST_FILE = Path("/app/streaming/playlist/radio.m3u")

def write_playlist_file(state: Dict[str, Any]):
    """Write the given radio state's queue to the playlist file for Liquidsoap"""
    try:
        audio_library = Path("/app/audio_library")

        # Build playlist with current song first, then queue
        playlist_lines = ["#EXTM3U"]

        # Add current song if playing
        if state["current_song"]:
            song_id = state["current_song"].get("id")
            title = state["current_song"].get("title", "Unknown")
            audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))
            if audio_files:
                playlist_lines.append(f"#EXTINF:-1,{title}")
                # Convert path for Liquidsoap container: /app/audio_library -> /audio_library
                liquidsoap_path = str(audio_files[0]).replace("/app/audio_library", "/audio_library")
                playlist_lines.append(liquidsoap_path)

        # Add queue
        for song in state["queue"]:
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
        print(f"Playlist updated: {len(playlist_lines) // 2} songs")
    except Exception as e:
        print(f"Error writing playlist: {e}")


async def get_radio_store() -> RadioStateStore:
    """Dependency to get or create the process-external radio state store"""
    global radio_store, db_manager
    if radio_store is None:
        if db_manager is None:
            db_manager = DatabaseManager()
            await db_manager.connect()
        radio_store = RadioStateStore(db_manager)
        await radio_store.ensure_initialized()
    return radio_store


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
#
# Runtime radio state (queue, now-playing, play/pause, position) and the active
# listener set are stored process-externally in PostgreSQL via RadioStateStore so
# they survive backend restarts and stay consistent across backend instances
# (issue #2). The helpers below mutate a plain state dict that the endpoints load
# from and save back to the store on each request.
def update_radio_position(state: Dict[str, Any]):
    """Update current playback position based on elapsed time (mutates state in place)"""
    if state["is_playing"] and state["current_song"]:
        elapsed = time.time() - state["last_update"]
        state["position"] += elapsed
        state["last_update"] = time.time()

        # Check if song finished (only if duration is valid)
        duration = state["current_song"].get("duration")
        if duration and duration > 0 and state["position"] >= duration:
            # Move to next song
            print(f"Song finished: {state['current_song'].get('title')} ({state['position']:.1f}s / {duration:.1f}s)")
            advance_to_next_song(state)


def advance_to_next_song(state: Dict[str, Any]):
    """Advance to the next song in queue (mutates state in place)"""
    if len(state["queue"]) > 0:
        state["current_song"] = state["queue"].pop(0)
        state["position"] = 0
        state["is_playing"] = True
        state["last_update"] = time.time()

        # Debug logging
        duration = state["current_song"].get("duration", "NOT SET")
        print(f"Now playing: {state['current_song'].get('title')} (duration: {duration}s)")

        # Update playlist file for Liquidsoap
        write_playlist_file(state)
    else:
        state["current_song"] = None
        state["position"] = 0
        state["is_playing"] = False
        print("Queue empty - stopping playback")

        # Update playlist file for Liquidsoap
        write_playlist_file(state)


async def auto_populate_queue(state: Dict[str, Any]):
    """Auto-populate queue with songs if it's running low (mutates state in place)"""
    if len(state["queue"]) < 5:
        try:
            # Use the agent to find good songs
            agent_instance = await get_agent()
            result = await agent_instance.search_songs("Find me some great songs to keep the vibe going", limit=10)

            # Add songs to queue
            for song in result["songs"]:
                if song not in state["queue"]:
                    # Normalize field names: duration_seconds -> duration
                    if "duration_seconds" in song and "duration" not in song:
                        song["duration"] = song["duration_seconds"]
                    state["queue"].append(song)
        except Exception as e:
            print(f"Error auto-populating queue: {e}")


async def register_listener(store: RadioStateStore, listener_id: str, state: Dict[str, Any]) -> bool:
    """Register a listener and start playback if this is the first one.

    Returns True if the radio state was mutated and should be persisted.
    """
    was_empty = await store.count_active_listeners() == 0
    await store.register_listener(listener_id)

    # If this is the first listener, start playing
    if was_empty and not state["is_playing"]:
        if state["current_song"] or len(state["queue"]) > 0:
            if not state["current_song"] and len(state["queue"]) > 0:
                advance_to_next_song(state)
            else:
                state["is_playing"] = True
                state["last_update"] = time.time()
            print(f"First listener connected - starting playback")
            return True
    return False


@app.get("/api/radio/state")
async def get_radio_state(
    listener_id: str = None,
    store: RadioStateStore = Depends(get_radio_store),
):
    """Get current radio state (synchronized for all listeners)"""
    try:
        state = await store.load_state()

        # Clean up stale listeners
        await store.cleanup_stale_listeners()

        # Generate listener ID if not provided
        if not listener_id:
            listener_id = str(uuid.uuid4())

        # Register this listener (may start playback)
        await register_listener(store, listener_id, state)

        # Update position based on elapsed time
        update_radio_position(state)

        # Auto-populate queue if needed
        await auto_populate_queue(state)

        # If no active listeners remain, pause the radio
        active_listeners = await store.count_active_listeners()
        if active_listeners == 0 and state["is_playing"]:
            state["is_playing"] = False
            print("No active listeners - pausing radio")

        await store.save_state(state)

        return {
            "current_song": state["current_song"],
            "queue": state["queue"][:10],  # Only send next 10 songs
            "is_playing": state["is_playing"],
            "position": state["position"],
            "queue_length": len(state["queue"]),
            "listener_id": listener_id,  # Return listener ID for future requests
            "active_listeners": active_listeners
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AddToQueueRequest(BaseModel):
    message: str  # Natural language request for songs


@app.post("/api/radio/queue/add")
async def add_to_queue(
    request: AddToQueueRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    store: RadioStateStore = Depends(get_radio_store),
):
    """Add songs to queue via DJ agent (all authenticated users)"""
    try:
        state = await store.load_state()

        # Use agent to find songs
        result = await agent.search_songs(request.message, limit=20)

        # Add to queue
        added_count = 0
        for song in result["songs"]:
            # Check if song not already in queue
            if not any(s.get("id") == song.get("id") for s in state["queue"]):
                # Normalize field names: duration_seconds -> duration
                if "duration_seconds" in song and "duration" not in song:
                    song["duration"] = song["duration_seconds"]
                state["queue"].append(song)
                added_count += 1

        # If nothing is playing, start playing
        if not state["current_song"] and len(state["queue"]) > 0:
            advance_to_next_song(state)
        elif added_count > 0:
            # Update playlist file even if we didn't start playback
            write_playlist_file(state)

        await store.save_state(state)

        return {
            "response": result["response"],
            "added_count": added_count,
            "queue_length": len(state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/radio/skip")
async def skip_song(store: RadioStateStore = Depends(get_radio_store)):
    """Skip to next song (editor/admin only)"""
    try:
        state = await store.load_state()

        advance_to_next_song(state)

        # Auto-populate if needed
        await auto_populate_queue(state)

        await store.save_state(state)

        return {
            "current_song": state["current_song"],
            "queue_length": len(state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class RemoveFromQueueRequest(BaseModel):
    song_id: int


@app.post("/api/radio/queue/remove")
async def remove_from_queue(
    request: RemoveFromQueueRequest,
    store: RadioStateStore = Depends(get_radio_store),
):
    """Remove a song from the queue (editor/admin only)"""
    try:
        state = await store.load_state()

        # Find and remove the song
        original_length = len(state["queue"])
        state["queue"] = [s for s in state["queue"] if s.get("id") != request.song_id]

        removed = original_length - len(state["queue"])

        if removed > 0:
            write_playlist_file(state)
            await store.save_state(state)

        return {
            "removed": removed > 0,
            "queue_length": len(state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/radio/play")
async def play_radio(store: RadioStateStore = Depends(get_radio_store)):
    """Start/resume radio playback (editor/admin only)"""
    try:
        state = await store.load_state()

        if not state["current_song"] and len(state["queue"]) > 0:
            advance_to_next_song(state)
        else:
            state["is_playing"] = True
            state["last_update"] = time.time()

        await store.save_state(state)

        return {"is_playing": state["is_playing"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/radio/pause")
async def pause_radio(store: RadioStateStore = Depends(get_radio_store)):
    """Pause radio playback (editor/admin only)"""
    try:
        state = await store.load_state()

        update_radio_position(state)
        state["is_playing"] = False

        await store.save_state(state)

        return {"is_playing": state["is_playing"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Radio Stream endpoint (HLS playlist)
@app.get("/stream")
async def radio_stream(request: Request, store: RadioStateStore = Depends(get_radio_store)):
    """
    Returns an HLS playlist for the radio stream.
    Can be used with any HLS-compatible player (VLC, browsers with hls.js, etc.)
    """
    try:
        state = await store.load_state()

        update_radio_position(state)

        # Auto-populate queue if needed
        await auto_populate_queue(state)

        await store.save_state(state)

        # Build base URL from request
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Build HLS playlist
        playlist_lines = [
            "#EXTM3U",
            "#EXT-X-VERSION:3",
            "#EXT-X-TARGETDURATION:600",  # Max segment duration (10 minutes)
            "#EXT-X-MEDIA-SEQUENCE:0",
        ]

        # Add current song if playing
        if state["current_song"]:
            duration = state["current_song"].get("duration", 180)
            title = state["current_song"].get("title", "Unknown")
            song_id = state["current_song"].get("id")

            playlist_lines.append(f"#EXTINF:{duration},{title}")
            playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

        # Add upcoming songs from queue
        for song in state["queue"][:10]:  # Next 10 songs
            duration = song.get("duration", 180)
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
async def radio_stream_m3u(request: Request, store: RadioStateStore = Depends(get_radio_store)):
    """
    Returns a simple M3U playlist for the radio stream.
    Compatible with most media players (VLC, Winamp, etc.)
    """
    try:
        state = await store.load_state()

        update_radio_position(state)

        # Auto-populate queue if needed
        await auto_populate_queue(state)

        await store.save_state(state)

        # Build base URL from request
        base_url = f"{request.url.scheme}://{request.url.netloc}"

        # Build M3U playlist
        playlist_lines = ["#EXTM3U"]

        # Add current song if playing
        if state["current_song"]:
            duration = int(state["current_song"].get("duration", 180))
            title = state["current_song"].get("title", "Unknown")
            song_id = state["current_song"].get("id")

            playlist_lines.append(f"#EXTINF:{duration},{title}")
            playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

        # Add upcoming songs from queue
        for song in state["queue"][:10]:
            duration = int(song.get("duration", 180))
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
