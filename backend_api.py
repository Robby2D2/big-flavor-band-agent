"""
FastAPI backend server for BigFlavor Band Agent
Bridges the Next.js frontend with the Python agent
"""
import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
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

class JsonLogFormatter(logging.Formatter):
    """Emit each log record as a single JSON object for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure leveled backend logging.

    LOG_LEVEL  controls verbosity (default INFO).
    LOG_FORMAT selects 'text' (default, human-readable) or 'json' (production).
    """
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler()
    if os.getenv("LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


configure_logging()
logger = logging.getLogger("backend-api")

# Long-lived singletons. These are constructed exactly once in the lifespan
# handler at startup (not lazily on first request), so the first request never
# pays cold-start and two concurrent first requests can't race an unlocked init.
agent: Optional[BigFlavorAgent] = None
rag: Optional[SongRAGSystem] = None
db_manager: Optional[DatabaseManager] = None

# Handle to the background task that owns the radio playback clock and queue
# top-up. Started in lifespan so playback advances and the queue refills
# independently of inbound requests; GET /api/radio/state and /stream stay
# side-effect-free reads.
radio_task: Optional[asyncio.Task] = None

# How often the background loop ticks the playback clock, and how often (in
# ticks) it runs the heavier agent/search queue top-up off the request path.
RADIO_TICK_INTERVAL = 1.0  # seconds
RADIO_TOPUP_EVERY_TICKS = 5


async def radio_background_loop():
    """Own the radio playback clock and queue top-up, independent of requests.

    Advances the playback position (rolling to the next song when one finishes)
    every tick, and refills the queue periodically. This is the single driver of
    playback time and top-up, so the stream keeps advancing and never runs dry
    whether or not any client is polling GET /api/radio/state. State lives in the
    process-external RadioStateStore (issue #2), so each tick loads, mutates, and
    saves it back.
    """
    logger.info("Radio background loop started")
    tick = 0
    try:
        while True:
            await asyncio.sleep(RADIO_TICK_INTERVAL)
            tick += 1
            try:
                store = await get_radio_store()
                state = await store.load_state()
                update_radio_position(state)
                if tick % RADIO_TOPUP_EVERY_TICKS == 0:
                    await auto_populate_queue(state)
                await store.save_state(state)
            except Exception:
                logger.exception("Radio background loop tick failed")
    except asyncio.CancelledError:
        logger.info("Radio background loop cancelled")
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the agent/RAG/DB singletons and start the radio background
    clock/top-up task at startup; release them all at shutdown."""
    global agent, rag, db_manager, radio_task

    logger.info("Startup: initializing backend singletons...")

    db_manager = DatabaseManager()
    await db_manager.connect()
    logger.info("Startup: DatabaseManager connected")

    rag = SongRAGSystem(db_manager, use_clap=True)
    logger.info("Startup: SongRAGSystem ready")

    agent = BigFlavorAgent()
    await agent.initialize()
    logger.info("Startup: BigFlavorAgent initialized")

    # Start the radio clock only after the DB is up — the loop loads/saves radio
    # state through the store, which needs the connected db_manager.
    radio_task = asyncio.create_task(radio_background_loop())
    logger.info("Startup: radio background loop scheduled")

    logger.info("Startup complete: backend ready to serve requests")

    yield

    logger.info("Shutdown: closing backend resources...")
    if radio_task is not None:
        radio_task.cancel()
        try:
            await radio_task
        except asyncio.CancelledError:
            pass
        logger.info("Shutdown: radio background loop stopped")
    # The agent owns its own DatabaseManager (created in BigFlavorAgent.initialize()),
    # so close that pool too, not just the backend's.
    if agent is not None and getattr(agent, "db_manager", None) is not None:
        await agent.db_manager.close()
        logger.info("Shutdown: agent DatabaseManager pool closed")
    if db_manager is not None:
        await db_manager.close()
        logger.info("Shutdown: DatabaseManager pool closed")
    agent = None
    rag = None
    db_manager = None
    logger.info("Shutdown complete: backend resources released")


app = FastAPI(title="BigFlavor Band Agent API", version="1.0.0", lifespan=lifespan)

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

# Radio state store (process-external, survives restarts and shared across
# backend instances) — issue #2. The agent/RAG/DB singletons are declared and
# initialized in the lifespan handler above.
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
        logger.info("Playlist updated: %d songs", len(playlist_lines) // 2)
    except Exception:
        logger.exception("Error writing playlist")


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
async def create_or_update_user(
    user: UserCreate,
    db: DatabaseManager = Depends(get_db)
):
    """Create or update a user in the database"""
    try:
        result = await db.upsert_user(
            user.id, user.email, user.name, user.picture
        )

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
async def get_user_role(
    user_id: str,
    db: DatabaseManager = Depends(get_db)
):
    """Get a user's role from the database"""
    try:
        role = await db.get_user_role(user_id)

        if role is None:
            raise HTTPException(status_code=404, detail="User not found")

        return {"role": role}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Admin endpoints
@app.get("/api/admin/users")
async def get_all_users(db: DatabaseManager = Depends(get_db)):
    """Get all users (admin only)"""
    try:
        results = await db.list_users()

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
async def update_user_role(
    request: UpdateRoleRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Update a user's role (admin only)"""
    try:
        # Validate role
        valid_roles = ['listener', 'editor', 'admin']
        if request.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")

        result = await db.set_user_role(request.user_id, request.role)

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
        logger.exception("Error in natural_language_search")
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
        lyrics = await db.get_song_lyrics(song_id)

        if lyrics is not None:
            return {"lyrics": lyrics}
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
            logger.info(
                "Song finished: %s (%.1fs / %.1fs)",
                state["current_song"].get("title"),
                state["position"],
                duration,
            )
            advance_to_next_song(state)


def advance_to_next_song(state: Dict[str, Any]):
    """Advance to the next song in queue (mutates state in place)"""
    if len(state["queue"]) > 0:
        state["current_song"] = state["queue"].pop(0)
        state["position"] = 0
        state["is_playing"] = True
        state["last_update"] = time.time()

        duration = state["current_song"].get("duration", "NOT SET")
        logger.info(
            "Now playing: %s (duration: %ss)",
            state["current_song"].get("title"),
            duration,
        )

        # Update playlist file for Liquidsoap
        write_playlist_file(state)
    else:
        state["current_song"] = None
        state["position"] = 0
        state["is_playing"] = False
        logger.info("Queue empty - stopping playback")

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
        except Exception:
            logger.exception("Error auto-populating queue")


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
            logger.info("First listener connected - starting playback")
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

        # Register this listener (may start playback for the first listener).
        # The playback clock and queue top-up are owned by radio_background_loop(),
        # so this read does NOT advance the song, mutate playback position, or
        # invoke the agent/search — it only registers presence.
        mutated = await register_listener(store, listener_id, state)

        # NOTE: playback is intentionally NOT paused when the listener count
        # drops to zero — the radio is a continuous broadcast driven by
        # radio_background_loop() (issue #5). active_listeners is reported for
        # observability only.
        active_listeners = await store.count_active_listeners()

        if mutated:
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
        # Read-only: the playback clock and queue top-up are driven by
        # radio_background_loop(), not by this stream request. We only load the
        # current state to render the playlist.
        state = await store.load_state()

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
        # Read-only: the playback clock and queue top-up are driven by
        # radio_background_loop(), not by this stream request. We only load the
        # current state to render the playlist.
        state = await store.load_state()

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
