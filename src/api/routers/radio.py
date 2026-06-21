"""Radio control + streaming routes.

Thin wrappers over the process-external radio state (RadioStateStore, issue #2)
and the playback helpers in ``src/api/radio_service.py``. The playback clock and
queue top-up are owned by the background loop (issue #5), so GET /api/radio/state
and the /stream endpoints are side-effect-free reads. Control routes (skip,
remove, play, pause) require the editor role (issue #1). Raw exceptions propagate
to the centralized error handlers (issue #9).
"""
import time
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response, FileResponse
from fastapi.concurrency import run_in_threadpool

from database import RadioStateStore
from src.agent.big_flavor_agent import BigFlavorAgent
from src.auth import require_role
from src.api.dependencies import (
    AddToQueueRequest,
    RemoveFromQueueRequest,
    get_radio_store,
    get_agent,
)
from src.api.radio_service import (
    register_listener,
    update_radio_position,
    advance_to_next_song,
    auto_populate_queue,
    write_playlist_file,
    _find_audio_file,
)

router = APIRouter()


@router.get("/api/radio/state")
async def get_radio_state(
    listener_id: str = None,
    store: RadioStateStore = Depends(get_radio_store),
):
    """Get current radio state (synchronized for all listeners)"""
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


@router.post("/api/radio/queue/add")
async def add_to_queue(
    request: AddToQueueRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    store: RadioStateStore = Depends(get_radio_store),
):
    """Add songs to queue via DJ agent (all authenticated users)"""
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


@router.post("/api/radio/skip")
async def skip_song(
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Skip to next song (editor/admin only)"""
    state = await store.load_state()

    advance_to_next_song(state)

    # Auto-populate if needed
    await auto_populate_queue(state)

    await store.save_state(state)

    return {
        "current_song": state["current_song"],
        "queue_length": len(state["queue"])
    }


@router.post("/api/radio/queue/remove")
async def remove_from_queue(
    request: RemoveFromQueueRequest,
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Remove a song from the queue (editor/admin only)"""
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


@router.post("/api/radio/play")
async def play_radio(
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Start/resume radio playback (editor/admin only)"""
    state = await store.load_state()

    if not state["current_song"] and len(state["queue"]) > 0:
        advance_to_next_song(state)
    else:
        state["is_playing"] = True
        state["last_update"] = time.time()

    await store.save_state(state)

    return {"is_playing": state["is_playing"]}


@router.post("/api/radio/pause")
async def pause_radio(
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Pause radio playback (editor/admin only)"""
    state = await store.load_state()

    update_radio_position(state)
    state["is_playing"] = False

    await store.save_state(state)

    return {"is_playing": state["is_playing"]}


# Radio Stream endpoint (HLS playlist)
@router.get("/stream")
async def radio_stream(request: Request, store: RadioStateStore = Depends(get_radio_store)):
    """
    Returns an HLS playlist for the radio stream.
    Can be used with any HLS-compatible player (VLC, browsers with hls.js, etc.)
    """
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


@router.get("/stream.m3u")
async def radio_stream_m3u(request: Request, store: RadioStateStore = Depends(get_radio_store)):
    """
    Returns a simple M3U playlist for the radio stream.
    Compatible with most media players (VLC, Winamp, etc.)
    """
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


@router.get("/api/audio/stream/{song_id}")
async def stream_audio(song_id: int):
    """
    Stream audio file for a song.

    Uses FileResponse so the file is sent off the event loop (no blocking
    read in the request path) and HTTP Range requests are honored natively
    (206 Partial Content), enabling seeking in the player.
    """
    # Run the filesystem lookup in a thread so the event loop is not blocked.
    audio_path = await run_in_threadpool(_find_audio_file, song_id)

    if audio_path is None:
        raise HTTPException(status_code=404, detail=f"Audio file for song {song_id} not found")

    return FileResponse(
        audio_path,
        media_type="audio/mpeg",
        headers={"Content-Disposition": f"inline; filename={audio_path.name}"},
    )
