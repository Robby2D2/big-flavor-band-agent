"""Radio playback/queue domain logic, extracted from the HTTP routing layer.

`RadioService` owns the in-process radio state (current song, queue,
play/pause, position), listener tracking, and the playlist-file writing for
Liquidsoap. The HTTP routes in `src/api/routers/radio.py` are thin wrappers
over this service.

Two radio invariants are preserved here:
- The playlist path rewrite `/app/audio_library/...` -> `/audio_library/...`
  (Liquidsoap's mount) happens in `_build_and_write_playlist`.
- `mksafe()`-wrapping of Liquidsoap sources lives in `streaming/radio.liq`
  (not this layer) and is untouched.
"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Playlist file path for Liquidsoap integration.
PLAYLIST_FILE = Path("/app/streaming/playlist/radio.m3u")

# Directory the per-song audio files live in (named "{song_id}_*.mp3"). The cwd
# in the container is /app, so this resolves to the same /app/audio_library
# mount the playlist writer uses.
AUDIO_LIBRARY_DIR = Path("audio_library")


def _build_and_write_playlist(current_song, queue, audio_library: Path, playlist_file: Path):
    """Build the Liquidsoap .m3u from a state snapshot and write it.

    Pure/synchronous: does the blocking filesystem work (directory glob + file
    write). Run off the event loop via RadioService.write_playlist_file() so a
    queue change never blocks other requests. Operates on a snapshot (not the
    live state) so it is safe to run in a worker thread.
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


def _find_audio_file(song_id: int, audio_library: Path) -> Optional[Path]:
    """Locate the audio file for a song id. Synchronous (does a directory glob)."""
    audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))
    return audio_files[0] if audio_files else None


class RadioService:
    """Holds radio state and the queue/playback logic behind the radio routes."""

    def __init__(self):
        self.radio_state = {
            "current_song": None,  # {song_id, title, started_at, duration}
            "queue": [],  # List of song objects
            "is_playing": False,
            "position": 0,  # Current position in seconds
            "last_update": time.time(),
        }
        # Track active listeners (listener_id -> last_ping_time)
        self.active_listeners = {}

    # --- Playlist writing -------------------------------------------------

    def write_playlist_file(self):
        """Schedule a non-blocking playlist write for Liquidsoap.

        Offloads the blocking glob + file write to a thread so the event loop
        is never stalled. All callers run on the event loop; the write is a
        fire-and-forget side effect, so callers do not await the result.
        """
        current_song = self.radio_state["current_song"]
        queue = list(self.radio_state["queue"])
        loop = asyncio.get_running_loop()
        loop.run_in_executor(
            None,
            _build_and_write_playlist,
            current_song,
            queue,
            Path("/app/audio_library"),
            PLAYLIST_FILE,
        )

    # --- Playback state ---------------------------------------------------

    def update_radio_position(self):
        """Update current playback position based on elapsed time."""
        if self.radio_state["is_playing"] and self.radio_state["current_song"]:
            elapsed = time.time() - self.radio_state["last_update"]
            self.radio_state["position"] += elapsed
            self.radio_state["last_update"] = time.time()

            # Check if song finished (only if duration is valid)
            duration = self.radio_state["current_song"].get("duration")
            if duration and duration > 0 and self.radio_state["position"] >= duration:
                # Move to next song
                print(f"Song finished: {self.radio_state['current_song'].get('title')} ({self.radio_state['position']:.1f}s / {duration:.1f}s)")
                self.advance_to_next_song()

    def advance_to_next_song(self):
        """Advance to the next song in queue."""
        if len(self.radio_state["queue"]) > 0:
            self.radio_state["current_song"] = self.radio_state["queue"].pop(0)
            self.radio_state["position"] = 0
            self.radio_state["is_playing"] = True
            self.radio_state["last_update"] = time.time()

            # Debug logging
            duration = self.radio_state["current_song"].get("duration", "NOT SET")
            print(f"Now playing: {self.radio_state['current_song'].get('title')} (duration: {duration}s)")

            # Update playlist file for Liquidsoap
            self.write_playlist_file()
        else:
            self.radio_state["current_song"] = None
            self.radio_state["position"] = 0
            self.radio_state["is_playing"] = False
            print("Queue empty - stopping playback")

            # Update playlist file for Liquidsoap
            self.write_playlist_file()

    async def auto_populate_queue(self, agent):
        """Auto-populate queue with songs if it's running low."""
        if len(self.radio_state["queue"]) < 5:
            try:
                result = await agent.search_songs("Find me some great songs to keep the vibe going", limit=10)

                # Add songs to queue
                for song in result["songs"]:
                    if song not in self.radio_state["queue"]:
                        # Normalize field names: duration_seconds -> duration
                        if "duration_seconds" in song and "duration" not in song:
                            song["duration"] = song["duration_seconds"]
                        self.radio_state["queue"].append(song)
            except Exception as e:
                print(f"Error auto-populating queue: {e}")

    # --- Listener tracking ------------------------------------------------

    def cleanup_stale_listeners(self):
        """Remove listeners that haven't pinged in 10+ seconds."""
        current_time = time.time()
        stale_threshold = 10  # seconds

        stale_listeners = [
            listener_id for listener_id, last_ping in self.active_listeners.items()
            if current_time - last_ping > stale_threshold
        ]

        for listener_id in stale_listeners:
            del self.active_listeners[listener_id]

        # If no active listeners remain, pause the radio
        if len(self.active_listeners) == 0 and self.radio_state["is_playing"]:
            self.radio_state["is_playing"] = False
            print("No active listeners - pausing radio")

    def register_listener(self, listener_id: str):
        """Register a listener as active."""
        was_empty = len(self.active_listeners) == 0
        self.active_listeners[listener_id] = time.time()

        # If this is the first listener, start playing
        if was_empty and not self.radio_state["is_playing"]:
            if self.radio_state["current_song"] or len(self.radio_state["queue"]) > 0:
                if not self.radio_state["current_song"] and len(self.radio_state["queue"]) > 0:
                    self.advance_to_next_song()
                else:
                    self.radio_state["is_playing"] = True
                    self.radio_state["last_update"] = time.time()
                print(f"First listener connected - starting playback")
