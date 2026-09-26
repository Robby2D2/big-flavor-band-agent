"""Radio playback/queue domain logic, extracted from the HTTP routing layer.

Runtime radio state (queue, now-playing, play/pause, position) and the active
listener set are stored process-externally in PostgreSQL via RadioStateStore
(issue #2), so they survive backend restarts and stay consistent across backend
instances. The helpers here mutate a plain state dict that callers load from and
save back to the store; the routes in ``src/api/routers/radio.py`` are thin
wrappers over these functions and the store.

What is playing is decided by the **stream**, not by this layer (issue #101).
Liquidsoap serves the metadata of the track actually on air over harbor; the
background loop asks every tick and reconciles the stored state against the
answer, so the page can never drift away from the audio. The queue is still ours:
we write it to the playlist Liquidsoap plays from, and drop a song out of it once
the stream has started playing it.

Queue top-up is driven by ``radio_background_loop`` (issue #5) — so HTTP reads
(GET /api/radio/state, /stream) stay side-effect-free.

Two radio invariants are preserved here:
- The playlist path rewrite ``/app/audio_library/...`` -> ``/audio_library/...``
  (Liquidsoap's mount) happens in ``_build_and_write_playlist``.
- ``mksafe()``-wrapping of Liquidsoap sources lives in ``streaming/radio.liq``
  (not this layer) and is untouched.
"""
import asyncio
import logging
import os
import re
import time
from pathlib import Path, PurePosixPath
from typing import Optional, Dict, Any, Tuple

import httpx

from src.api.dependencies import get_agent, get_db, get_radio_store
from src.auth import Caller, role_at_least

logger = logging.getLogger("backend-api")

# Playlist file path for Liquidsoap integration.
PLAYLIST_FILE = Path("/app/streaming/playlist/radio.m3u")

# Directory the per-song audio files live in (named "{song_id}_*.mp3"). The cwd
# in the container is /app, so this resolves to the same /app/audio_library
# mount the playlist writer uses.
AUDIO_LIBRARY_DIR = Path("audio_library")

# Published-version path overrides ({song_id: audio_path}), seeded from
# song_versions at startup and refreshed when a producer publishes a new version
# (issue #30). When a song has a published version, its file is served by the
# radio playlist and /api/audio/stream instead of the default
# "{song_id}_*.mp3" glob. Kept in process memory so the synchronous playlist
# writer (which runs in a worker thread) never has to touch the DB.
_published_version_paths: Dict[int, str] = {}


def set_published_version_paths(paths: Dict[int, str]) -> None:
    """Replace the published-version path overrides (full refresh)."""
    global _published_version_paths
    _published_version_paths = dict(paths)


def set_published_version_path(song_id: int, audio_path: str) -> None:
    """Record/replace the published-version override for one song."""
    _published_version_paths[song_id] = audio_path

# How often the background loop asks the stream what it is playing, and how often
# (in ticks) it runs the heavier agent/search queue top-up off the request path.
RADIO_TICK_INTERVAL = 1.0  # seconds
RADIO_TOPUP_EVERY_TICKS = 5

# Where the stream answers "what is on the air" and "skip this track" — the harbor
# listener in streaming/radio.liq, on the Docker network only. Configurable so a
# non-Compose deployment can point elsewhere; no secret, so a default is fine.
LIQUIDSOAP_HARBOR_URL = os.environ.get("LIQUIDSOAP_HARBOR_URL", "http://liquidsoap:8080")

# The stream is on the same Docker network and answers from memory, so a slow
# reply means something is wrong; a tick must not queue up behind it.
ON_AIR_TIMEOUT_SECONDS = 2.0


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
            # Prefer the published version's file (issue #30); fall back to the
            # catalog "{song_id}_*.mp3" glob.
            published = _resolve_published_file(song_id)
            source_path = None
            if published is not None:
                source_path = str(published)
            else:
                audio_files = list(audio_library.glob(f"{song_id}_*.mp3"))
                if audio_files:
                    source_path = str(audio_files[0])
            if source_path:
                playlist_lines.append(f"#EXTINF:-1,{title}")
                # Convert path for Liquidsoap container: /app/audio_library -> /audio_library
                liquidsoap_path = source_path.replace("/app/audio_library", "/audio_library")
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
    run on the event loop (async request handlers, or the radio background loop).
    The write is a fire-and-forget side effect, so callers do not await the result.
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


def _resolve_published_file(song_id) -> Optional[Path]:
    """Return the published-version file for a song id if one exists on disk.

    The override stores absolute container paths (/app/audio_library/...) but the
    glob fallback resolves relative to the cwd (/app); accept either form.
    """
    try:
        sid = int(song_id)
    except (TypeError, ValueError):
        return None
    override = _published_version_paths.get(sid)
    if override:
        path = Path(override)
        if path.exists():
            return path
    return None


def _find_audio_file(song_id: int) -> Optional[Path]:
    """Locate the audio file for a song id. Synchronous (does a directory glob).

    Prefers the published version's file (issue #30) when one is set; otherwise
    falls back to the catalog "{song_id}_*.mp3" glob.
    """
    published = _resolve_published_file(song_id)
    if published is not None:
        return published
    audio_files = list(AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    return audio_files[0] if audio_files else None


# --- Queue attribution ----------------------------------------------------
#
# A listener may remove a queued song they added themselves, but nobody else's
# (ACCT-05, ACCT-15). That needs the queue to remember who added each entry, so a
# queue entry carries ADDED_BY. It needs no migration and no new table: the queue
# lives inside the radio_state JSONB the store already round-trips, so the
# attribution survives a backend restart with the rest of the state (RAD-04,
# RAD-13).
#
# Entries with no recorded adder are normal, not a defect: everything queued before
# this existed, everything the background top-up adds, and everything the DJ queues
# (the agent path carries no verified identity). RAD-13 makes them nobody's own, so
# only an editor or admin may remove them.

ADDED_BY = "added_by"


def attribute_queue_entry(song: Dict[str, Any], user_id: Optional[str]) -> Dict[str, Any]:
    """Stamp a song about to be queued with who added it. Mutates and returns it."""
    if user_id:
        song[ADDED_BY] = user_id
    return song


def may_remove_from_queue(song: Dict[str, Any], caller: Caller) -> bool:
    """Whether ``caller`` is allowed to remove this queued song.

    Editors and admins may remove anything. Everyone else may remove only what they
    added themselves, which means both sides of the comparison have to be known: an
    unidentified caller or an unattributed song is a refusal, not a match (ACCT-04,
    RAD-13).
    """
    if role_at_least(caller.role, "editor"):
        return True

    adder = song.get(ADDED_BY)
    return bool(adder) and bool(caller.user_id) and adder == caller.user_id


def queue_entry_for_display(
    song: Optional[Dict[str, Any]], caller: Caller
) -> Optional[Dict[str, Any]]:
    """A queue entry as the page may see it: whether *this* caller added it, never who did.

    The adder's account id stays server-side. The page needs only to know whether the
    remove control is this user's to offer; broadcasting every listener's account id
    to every other listener is not part of that. The flag is for drawing the control
    — the removal itself is authorized against the stored adder (ACCT-03, ACCT-04).
    """
    if song is None:
        return None

    entry = {key: value for key, value in song.items() if key != ADDED_BY}
    adder = song.get(ADDED_BY)
    entry["added_by_me"] = bool(adder) and bool(caller.user_id) and adder == caller.user_id
    return entry


# --- What is on the air ---------------------------------------------------

# Catalog audio files are named "{song_id}_<title>.mp3", which is what makes the
# filename the stream reports a usable identity.
_CATALOG_FILENAME = re.compile(r"^(\d+)_")


def song_id_from_filename(filename: Optional[str]) -> Optional[int]:
    """Map the file the stream is playing back to a catalog song id.

    The filename is the identity, not the Icecast title: a title is ID3 text that
    cannot be mapped back to a song reliably, while the file on disk is the one
    the playlist writer chose. Returns None for anything unrecognisable — a
    session render, a produced file nobody published, junk.
    """
    if not filename:
        return None
    name = PurePosixPath(str(filename)).name
    match = _CATALOG_FILENAME.match(name)
    if match:
        return int(match.group(1))
    # A published version (issue #30) is served from its own path, which need not
    # carry the song id, so fall back to the overrides the playlist writer uses.
    for song_id, path in _published_version_paths.items():
        if PurePosixPath(path).name == name:
            return song_id
    return None


async def fetch_on_air() -> Optional[Dict[str, Any]]:
    """Ask the stream what it is broadcasting.

    Returns the harbor payload (``filename``, ``title``, ``source``, ``elapsed``,
    ``remaining``) or None when the stream cannot be reached — which the caller
    reports as "unknown" rather than presenting a guess.
    """
    try:
        async with httpx.AsyncClient(timeout=ON_AIR_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{LIQUIDSOAP_HARBOR_URL}/on-air")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        # Logged by the caller on the transition only, so a stream that stays down
        # does not write a line a second.
        logger.debug("Could not read on-air metadata: %s", exc)
        return None


async def skip_on_air() -> bool:
    """Skip the track the stream is playing. False when the stream can't be reached.

    Skipping has to move the audio; relabelling the state would leave the listener
    hearing the song they asked to be rid of.
    """
    try:
        async with httpx.AsyncClient(timeout=ON_AIR_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{LIQUIDSOAP_HARBOR_URL}/skip")
            response.raise_for_status()
        return True
    except Exception:
        logger.warning("Could not skip the stream at %s", LIQUIDSOAP_HARBOR_URL, exc_info=True)
        return False


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _load_catalog_song(song_id: int) -> Optional[Dict[str, Any]]:
    """The queue-shaped dict for a catalog song the stream chose on its own.

    Only the fields the radio state carries: the whole row holds dates, which do
    not survive the JSONB round-trip the store does.
    """
    try:
        db = await get_db()
        song = await db.get_song(song_id)
    except Exception:
        logger.exception("Could not look up on-air song %s", song_id)
        return None
    if not song:
        return None
    return {
        "id": song["id"],
        "title": song.get("title", "Unknown"),
        "duration": song.get("duration_seconds"),
    }


def _song_from_stream(song_id: int, on_air: Dict[str, Any]) -> Dict[str, Any]:
    """The queue-shaped dict for on-air audio the catalog has no row for.

    The stream picks its fallback music off the filesystem, not out of the catalog,
    and the two do not agree: 74 of the 1,415 playable "{song_id}_*.mp3" files have
    no ``songs`` row (issue #104). Reporting those as nothing playing would put the
    radio page at "nothing is on the air" over audible music (RAD-05), so the track
    is named from what the stream itself knows about the file. Duration is left to
    the length the stream reports (``stream_duration``), which is the same source
    the page already uses for catalog songs with no duration (CAT-02).
    """
    title = str(on_air.get("title") or "").strip()
    if not title:
        # No ID3 title: the filename is "{song_id}_Some_Title.mp3", which is a
        # worse name than a tag but a much better one than silence.
        stem = PurePosixPath(str(on_air.get("filename") or "")).stem
        title = re.sub(rf"^{song_id}_", "", stem).replace("_", " ").strip()
    return {"id": song_id, "title": title or f"Song {song_id}", "duration": None}


async def resolve_on_air_song(
    on_air: Dict[str, Any],
    queue: list,
    current_song: Optional[Dict[str, Any]] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """The song on the air and where it came from ("queue" or "fallback").

    Where it came from is the stream's own answer, not a guess: each Liquidsoap
    source tags its tracks (``bigflavor_source``), because the playlist holds the
    current song as well as the queue and can replay it, so "is it still in our
    queue?" cannot tell the two apart.

    A song still in the queue is returned as its own queue entry, so the display
    keeps the fields the queue already carried. Anything else is looked up in the
    catalog, and named from the stream's own metadata when the catalog has no row
    for it, so audible audio is never reported as nothing playing (RAD-02's visible
    form) — including music the stream picked itself once the queue drained.
    """
    song_id = song_id_from_filename(on_air.get("filename"))
    if song_id is None:
        return None, None
    source = "fallback" if on_air.get("source") == "fallback" else "queue"
    queued = next((s for s in queue if s.get("id") == song_id), None)
    if queued is not None:
        return queued, source
    if current_song is not None and current_song.get("id") == song_id:
        # Already the song we are reporting: reconciliation runs every second, and a
        # song is on the air for minutes, so re-reading the catalog row each tick
        # would be one query a second for an answer we already hold.
        return current_song, source
    song = await _load_catalog_song(song_id)
    return (song or _song_from_stream(song_id, on_air)), source


def reconcile_with_stream(
    state: Dict[str, Any],
    on_air: Dict[str, Any],
    song: Optional[Dict[str, Any]],
    source: Optional[str],
) -> bool:
    """Make the radio state agree with the audio on the air (mutates state).

    This replaces the simulated clock that used to decide what was playing (issue
    #101). Position is the stream's own elapsed time, read fresh every tick, so it
    cannot accumulate error; and a song with no catalog duration can no longer pin
    the display, because nothing here compares a position against a duration.

    Returns True when the queue changed and the playlist needs rewriting.
    """
    state["stream_known"] = True
    state["last_update"] = time.time()

    elapsed = _as_float(on_air.get("elapsed"))
    remaining = _as_float(on_air.get("remaining"))
    state["position"] = elapsed if elapsed is not None and elapsed >= 0 else 0
    # Liquidsoap reports a negative remaining when it does not know the track
    # length. When it does know, this is a duration for songs the catalog has none
    # for (CAT-02) — kept beside the song rather than written into it, so catalog
    # data stays catalog data.
    if elapsed is not None and remaining is not None and elapsed >= 0 and remaining >= 0:
        state["stream_duration"] = elapsed + remaining
    else:
        state["stream_duration"] = None

    if song is None:
        # Audio whose file carries no song id at all (a session render, a produced
        # file nobody published). Say nothing rather than keep naming whatever was
        # playing before.
        state["current_song"] = None
        state["current_song_source"] = None
        return False

    was_idle = state["current_song"] is None
    # The stream has started it, so it is no longer up next. Keyed on membership
    # rather than on the source label, so the queue drains as the audio plays.
    before = len(state["queue"])
    state["queue"] = [s for s in state["queue"] if s.get("id") != song.get("id")]
    queue_changed = len(state["queue"]) != before

    state["current_song"] = song
    state["current_song_source"] = source
    if was_idle:
        # Audio is on the air and nothing was playing: the broadcast is live
        # (issue #79). An explicit pause keeps current_song set, so this cannot
        # resume one.
        state["is_playing"] = True

    return queue_changed


def mark_stream_unknown(state: Dict[str, Any]) -> None:
    """Record that the stream could not be asked what it is playing (mutates state).

    The stored current song is left alone — it is what the playlist is built from
    — but ``stream_known`` is False, and the radio page reports the current song as
    unknown rather than one that may already be wrong (PLAT-07).
    """
    if state.get("stream_known", True):
        logger.warning(
            "Cannot reach the stream at %s to ask what is playing — reporting radio "
            "state as unknown until it answers",
            LIQUIDSOAP_HARBOR_URL,
        )
    state["stream_known"] = False
    state["last_update"] = time.time()


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


# --- Background reconciliation -------------------------------------------

async def radio_background_loop():
    """Keep the stored radio state in agreement with the stream, and top the queue up.

    Every tick asks the stream what it is broadcasting and reconciles the state
    against the answer (issue #101), so the current song, its position and the
    queue are derived from the audio rather than from a clock of our own. Refills
    the queue periodically. State lives in the process-external RadioStateStore
    (issue #2), so each tick loads, mutates and saves it back — which is also why
    a backend restart needs no recovery step: the next tick simply asks again
    (RAD-04, PLAT-12).
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

                playlist_dirty = False
                on_air = await fetch_on_air()
                if on_air is None:
                    mark_stream_unknown(state)
                else:
                    song, source = await resolve_on_air_song(
                        on_air, state["queue"], state["current_song"]
                    )
                    playlist_dirty = reconcile_with_stream(state, on_air, song, source)

                if tick % RADIO_TOPUP_EVERY_TICKS == 0:
                    queued_before = len(state["queue"])
                    await auto_populate_queue(state)
                    playlist_dirty = playlist_dirty or len(state["queue"]) != queued_before

                if playlist_dirty:
                    write_playlist_file(state)
                await store.save_state(state)
            except Exception:
                logger.exception("Radio background loop tick failed")
    except asyncio.CancelledError:
        logger.info("Radio background loop cancelled")
        raise
