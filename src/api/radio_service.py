"""Radio playback/queue domain logic, extracted from the HTTP routing layer.

Runtime radio state (queue, now-playing, play/pause, position) and the active
listener set are stored process-externally in PostgreSQL via RadioStateStore
(issue #2), so they survive backend restarts and stay consistent across backend
instances. The helpers here mutate a plain state dict that callers load from and
save back to the store; the routes in ``src/api/routers/radio.py`` are thin
wrappers over these functions and the store.

The playback clock and queue top-up are driven by ``radio_background_loop`` —
the single owner of playback time and top-up (issue #5) — so HTTP reads
(GET /api/radio/state, /stream) stay side-effect-free.

Two radio invariants are preserved here:
- The playlist path rewrite ``/app/audio_library/...`` -> ``/audio_library/...``
  (Liquidsoap's mount) happens in ``_build_and_write_playlist``.
- ``mksafe()``-wrapping of Liquidsoap sources lives in ``streaming/radio.liq``
  (not this layer) and is untouched.
"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Any

from database import RadioStateStore
from src.api.dependencies import get_agent, get_radio_store

logger = logging.getLogger("backend-api")

# Playlist file path for Liquidsoap integration.
PLAYLIST_FILE = Path("/app/streaming/playlist/radio.m3u")

# Directory the per-song audio files live in (named "{song_id}_*.mp3"). The cwd
# in the container is /app, so this resolves to the same /app/audio_library
# mount the playlist writer uses.
AUDIO_LIBRARY_DIR = Path("audio_library")

# How often the background loop ticks the playback clock, and how often (in
# ticks) it runs the heavier agent/search queue top-up off the request path.
RADIO_TICK_INTERVAL = 1.0  # seconds
RADIO_TOPUP_EVERY_TICKS = 5


# --- Playlist writing -----------------------------------------------------

def _build_and_write_playlist(current_song, queue, audio_library: Path, playlist_file: Path):
    """Build the Liquidsoap .m3u from a state snapshot and write it.

    Pure/synchronous: does the blocking filesystem work (directory glob + file
    write). Run off the event loop via write_playlist_file() so a queue change
    never blocks other requests. Operates on a snapshot (not the live radio
    state) so it is safe to run in a worker thread.
    """
    try:
        playlist_lines = ["#EXTM3U"]

        # Current song first, then the queue.
        for song in ([current_song] if current_song else []) + queue:
            song_id = song.get("id")
            title = song.get("title", "Unknown")
            audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))
            if audio_files:
                playlist_lines.append(f"#EXTINF:-1,{title}")
                # Convert path for Liquidsoap container: /app/audio_library -> /audio_library
                liquidsoap_path = str(audio_files[0]).replace("/app/audio_library", "/audio_library")
                playlist_lines.append(liquidsoap_path)

        playlist_file.parent.mkdir(parents=True, exist_ok=True)
        playlist_file.write_text("\n".join(playlist_lines))
        logger.info("Playlist updated: %d songs", len(playlist_lines) // 2)
    except Exception:
        logger.exception("Error writing playlist")


def write_playlist_file(state: Dict[str, Any]):
    """Schedule a non-blocking playlist write for Liquidsoap.

    Offloads the blocking glob + file write to a thread so the event loop is
    never stalled. Operates on a snapshot of the given radio state; all callers
    run on the event loop (async request handlers, or the radio background loop,
    directly or via advance_to_next_song). The write is a fire-and-forget side
    effect, so callers do not await the result.
    """
    current_song = state["current_song"]
    queue = list(state["queue"])
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        None,
        _build_and_write_playlist,
        current_song,
        queue,
        Path("/app/audio_library"),
        PLAYLIST_FILE,
    )


def _find_audio_file(song_id: int) -> Optional[Path]:
    """Locate the audio file for a song id. Synchronous (does a directory glob)."""
    audio_files = list(AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    return audio_files[0] if audio_files else None


# --- Playback state -------------------------------------------------------

def update_radio_position(state: Dict[str, Any]):
    """Update current playback position based on elapsed time (mutates state in place)."""
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
    """Advance to the next song in queue (mutates state in place)."""
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
    """Auto-populate queue with songs if it's running low (mutates state in place)."""
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


# --- Listener tracking ----------------------------------------------------

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


# --- Background clock -----------------------------------------------------

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
