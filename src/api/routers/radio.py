"""Radio control + streaming routes — thin wrappers over RadioService."""
import time
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response, FileResponse
from fastapi.concurrency import run_in_threadpool

from src.agent.big_flavor_agent import BigFlavorAgent
from src.api.dependencies import (
    AddToQueueRequest,
    RemoveFromQueueRequest,
    get_agent,
)
from src.api.radio_service import RadioService, _find_audio_file

router = APIRouter()

# Single shared radio service instance for the process.
radio_service = RadioService()


@router.get("/api/radio/state")
async def get_radio_state(listener_id: str = None):
    """Get current radio state (synchronized for all listeners)"""
    try:
        # Clean up stale listeners
        radio_service.cleanup_stale_listeners()

        # Generate listener ID if not provided
        if not listener_id:
            listener_id = str(uuid.uuid4())

        # Register this listener
        radio_service.register_listener(listener_id)

        # Update position based on elapsed time
        radio_service.update_radio_position()

        # Auto-populate queue if needed
        agent = await get_agent()
        await radio_service.auto_populate_queue(agent)

        state = radio_service.radio_state
        return {
            "current_song": state["current_song"],
            "queue": state["queue"][:10],  # Only send next 10 songs
            "is_playing": state["is_playing"],
            "position": state["position"],
            "queue_length": len(state["queue"]),
            "listener_id": listener_id,  # Return listener ID for future requests
            "active_listeners": len(radio_service.active_listeners)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/radio/queue/add")
async def add_to_queue(
    request: AddToQueueRequest,
    agent: BigFlavorAgent = Depends(get_agent)
):
    """Add songs to queue via DJ agent (all authenticated users)"""
    try:
        # Use agent to find songs
        result = await agent.search_songs(request.message, limit=20)

        state = radio_service.radio_state

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
            radio_service.advance_to_next_song()
        elif added_count > 0:
            # Update playlist file even if we didn't start playback
            radio_service.write_playlist_file()

        return {
            "response": result["response"],
            "added_count": added_count,
            "queue_length": len(state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/radio/skip")
async def skip_song():
    """Skip to next song (editor/admin only)"""
    try:
        radio_service.advance_to_next_song()

        # Auto-populate if needed
        agent = await get_agent()
        await radio_service.auto_populate_queue(agent)

        return {
            "current_song": radio_service.radio_state["current_song"],
            "queue_length": len(radio_service.radio_state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/radio/queue/remove")
async def remove_from_queue(request: RemoveFromQueueRequest):
    """Remove a song from the queue (editor/admin only)"""
    try:
        state = radio_service.radio_state
        # Find and remove the song
        original_length = len(state["queue"])
        state["queue"] = [s for s in state["queue"] if s.get("id") != request.song_id]

        removed = original_length - len(state["queue"])

        return {
            "removed": removed > 0,
            "queue_length": len(state["queue"])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/radio/play")
async def play_radio():
    """Start/resume radio playback (editor/admin only)"""
    try:
        state = radio_service.radio_state
        if not state["current_song"] and len(state["queue"]) > 0:
            radio_service.advance_to_next_song()
        else:
            state["is_playing"] = True
            state["last_update"] = time.time()

        return {"is_playing": state["is_playing"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/radio/pause")
async def pause_radio():
    """Pause radio playback (editor/admin only)"""
    try:
        radio_service.update_radio_position()
        radio_service.radio_state["is_playing"] = False

        return {"is_playing": radio_service.radio_state["is_playing"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Radio Stream endpoint (HLS playlist)
@router.get("/stream")
async def radio_stream(request: Request):
    """
    Returns an HLS playlist for the radio stream.
    Can be used with any HLS-compatible player (VLC, browsers with hls.js, etc.)
    """
    try:
        radio_service.update_radio_position()

        # Auto-populate queue if needed
        agent = await get_agent()
        await radio_service.auto_populate_queue(agent)

        state = radio_service.radio_state

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


@router.get("/stream.m3u")
async def radio_stream_m3u(request: Request):
    """
    Returns a simple M3U playlist for the radio stream.
    Compatible with most media players (VLC, Winamp, etc.)
    """
    try:
        radio_service.update_radio_position()

        # Auto-populate queue if needed
        agent = await get_agent()
        await radio_service.auto_populate_queue(agent)

        state = radio_service.radio_state

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


@router.get("/api/audio/stream/{song_id}")
async def stream_audio(song_id: int):
    """
    Stream audio file for a song.

    Uses FileResponse so the file is sent off the event loop (no blocking
    read in the request path) and HTTP Range requests are honored natively
    (206 Partial Content), enabling seeking in the player.
    """
    try:
        # Resolve the audio library dir from the backend_api module at call time
        # so it remains patchable (the in-repo test monkeypatches it there).
        import backend_api

        # Run the filesystem lookup in a thread so the event loop is not blocked.
        audio_path = await run_in_threadpool(
            _find_audio_file, song_id, backend_api.AUDIO_LIBRARY_DIR
        )

        if audio_path is None:
            raise HTTPException(status_code=404, detail=f"Audio file for song {song_id} not found")

        return FileResponse(
            audio_path,
            media_type="audio/mpeg",
            headers={"Content-Disposition": f"inline; filename={audio_path.name}"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
