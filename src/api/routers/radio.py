"""Radio control + streaming routes.

Thin wrappers over the process-external radio state (RadioStateStore, issue #2)
and the playback helpers in ``src/api/radio_service.py``. What is playing is
reconciled against the stream by the background loop (issue #101), and the queue
top-up is owned by it too (issue #5), so GET /api/radio/state and the /stream
endpoints are side-effect-free reads. Skip and play/pause require the editor role
(issue #1); removing a queued song is allowed to whoever added it and to editors
above that (issue #102), so it is authorized against the queue's own attribution
rather than on rank alone. Raw exceptions propagate to the centralized error
handlers (issue #9).
"""
import uuid

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import Response, FileResponse
from fastapi.concurrency import run_in_threadpool

from database import RadioStateStore
from src.agent.big_flavor_agent import BigFlavorAgent
from src.auth import Caller, optional_caller, require_caller, require_role
from src.api.dependencies import (
    AddToQueueRequest,
    RemoveFromQueueRequest,
    get_radio_store,
    get_agent,
)
from src.api.radio_service import (
    attribute_queue_entry,
    auto_populate_queue,
    may_remove_from_queue,
    queue_entry_for_display,
    skip_on_air,
    write_playlist_file,
    _find_audio_file,
)

router = APIRouter()


@router.get("/api/radio/state")
async def get_radio_state(
    listener_id: str = None,
    store: RadioStateStore = Depends(get_radio_store),
    caller: Caller = Depends(optional_caller),
):
    """Get current radio state (synchronized for all listeners)"""
    state = await store.load_state()

    # Clean up stale listeners
    await store.cleanup_stale_listeners()

    # Generate listener ID if not provided
    if not listener_id:
        listener_id = str(uuid.uuid4())

    # Presence only. What is playing is reconciled against the stream by
    # radio_background_loop(), and the queue top-up is owned by it too, so this
    # read does NOT advance the song, mutate playback position, or invoke the
    # agent/search. A listener arriving used to start playback; the stream decides
    # now (issue #101).
    await store.register_listener(listener_id)

    # NOTE: playback is intentionally NOT paused when the listener count
    # drops to zero — the radio is a continuous broadcast driven by
    # radio_background_loop() (issue #5). active_listeners is reported for
    # observability only.
    active_listeners = await store.count_active_listeners()

    # Each entry says whether *this* caller added it, so the page knows which
    # remove controls are theirs to offer; the stored adder id never leaves the
    # backend (issue #102).
    return {
        "current_song": queue_entry_for_display(state["current_song"], caller),
        "queue": [
            queue_entry_for_display(song, caller) for song in state["queue"][:10]
        ],  # Only send next 10 songs
        "is_playing": state["is_playing"],
        "position": state["position"],
        "queue_length": len(state["queue"]),
        "listener_id": listener_id,  # Return listener ID for future requests
        "active_listeners": active_listeners,
        # Whether the stream could be asked what it is playing, and whether what it
        # is playing came from the queue or from the fallback source (issue #101).
        # A page that cannot trust current_song has to be able to say so.
        "stream_known": state.get("stream_known", False),
        "current_song_source": state.get("current_song_source"),
        # The length the stream reports for the track on air, for songs the catalog
        # has no duration for (CAT-02).
        "stream_duration": state.get("stream_duration"),
    }


@router.post("/api/radio/queue/add")
async def add_to_queue(
    request: AddToQueueRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    store: RadioStateStore = Depends(get_radio_store),
    caller: Caller = Depends(optional_caller),
):
    """Add songs to queue via DJ agent (all authenticated users).

    Who may add is unchanged (RAD-06). Each song is stamped with whoever added it so
    they can take their own add back later without an editor (ACCT-05, RAD-13); a
    caller the BFF did not vouch for adds anonymously, and an anonymous add is
    nobody's own.
    """
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
            state["queue"].append(attribute_queue_entry(song, caller.user_id))
            added_count += 1

    # The playlist is what the stream plays from, so a queue change reaches the air
    # by being written (RAD-08). Which song is then playing comes back from the
    # stream on the next tick, not from a guess made here.
    if added_count > 0:
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
    """Skip the track on the stream (editor/admin only).

    Skips the audio itself rather than relabelling our own state (issue #101): a
    relabel left the listener hearing the song they had just skipped. The stream
    keeps playing afterwards -- the fallback source takes over when the queue is
    empty (RAD-10). If the stream cannot be reached the skip failed, and says so
    rather than appearing to succeed (RAD-09).
    """
    if not await skip_on_air():
        raise HTTPException(
            status_code=503,
            detail="Could not reach the stream to skip the current song",
        )

    state = await store.load_state()

    # Auto-populate if needed
    await auto_populate_queue(state)
    write_playlist_file(state)

    await store.save_state(state)

    return {
        "skipped": True,
        "queue_length": len(state["queue"])
    }


@router.post("/api/radio/queue/remove")
async def remove_from_queue(
    request: RemoveFromQueueRequest,
    store: RadioStateStore = Depends(get_radio_store),
    caller: Caller = Depends(require_caller("listener")),
):
    """Remove a song from the queue.

    An editor or admin may remove any queued song; anyone else only one they added
    themselves (ACCT-05, ACCT-15). The check is made here rather than only in the UI,
    so hiding the control is a courtesy and this is the authority (ACCT-04).
    """
    state = await store.load_state()

    target = next((s for s in state["queue"] if s.get("id") == request.song_id), None)

    if target is None:
        # Not a refusal: the stream plays songs out of the queue as it goes, so a
        # song that has just left it is a race, not an attempt to remove
        # somebody else's.
        return {"removed": False, "queue_length": len(state["queue"])}

    if not may_remove_from_queue(target, caller):
        raise HTTPException(
            status_code=403,
            detail="You can only remove songs you added yourself",
        )

    state["queue"] = [s for s in state["queue"] if s.get("id") != request.song_id]

    write_playlist_file(state)
    await store.save_state(state)

    return {
        "removed": True,
        "queue_length": len(state["queue"])
    }


@router.post("/api/radio/play")
async def play_radio(
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Start/resume radio playback (editor/admin only).

    The stream is always broadcasting; this clears the paused flag so the page
    reads LIVE again. What is playing still comes from the stream.
    """
    state = await store.load_state()

    state["is_playing"] = True

    await store.save_state(state)

    return {"is_playing": state["is_playing"]}


@router.post("/api/radio/pause")
async def pause_radio(
    store: RadioStateStore = Depends(get_radio_store),
    _role: str = Depends(require_role("editor")),
):
    """Pause radio playback (editor/admin only)."""
    state = await store.load_state()

    state["is_playing"] = False

    await store.save_state(state)

    return {"is_playing": state["is_playing"]}


# Nominal segment length for the stream playlists when nothing knows the real one.
# A song is not required to carry a duration (CAT-02), and `.get("duration", 180)`
# does not cover that: the key is present with a null value.
DEFAULT_PLAYLIST_DURATION = 180


def _playlist_duration(song: dict) -> int:
    duration = song.get("duration")
    try:
        seconds = int(duration)
    except (TypeError, ValueError):
        return DEFAULT_PLAYLIST_DURATION
    return seconds if seconds > 0 else DEFAULT_PLAYLIST_DURATION


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
        duration = _playlist_duration(state["current_song"])
        title = state["current_song"].get("title", "Unknown")
        song_id = state["current_song"].get("id")

        playlist_lines.append(f"#EXTINF:{duration},{title}")
        playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

    # Add upcoming songs from queue
    for song in state["queue"][:10]:  # Next 10 songs
        duration = _playlist_duration(song)
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
        duration = _playlist_duration(state["current_song"])
        title = state["current_song"].get("title", "Unknown")
        song_id = state["current_song"].get("id")

        playlist_lines.append(f"#EXTINF:{duration},{title}")
        playlist_lines.append(f"{base_url}/api/audio/stream/{song_id}")

    # Add upcoming songs from queue
    for song in state["queue"][:10]:
        duration = _playlist_duration(song)
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
