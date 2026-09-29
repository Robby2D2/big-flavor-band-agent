"""Produce a session's song group: the takes become one catalog song's versions.

This is the human import SESS-10 waits for. Review only groups takes into songs;
producing a group is the explicit step that brings one into the catalog:

* **One new song per group** (SESS-19). A session never matches its takes to a
  song already in the catalog — a re-recording is a new song on purpose.
* **Every take that was not discarded becomes a version**, and **none is the
  default** (SESS-15). Choosing it happens on the produce page, and until then
  the song is listed nowhere a listener looks (SESS-20).
* **Producing again only adds.** A take that already became a version is
  skipped, so a take moved into the group later arrives on the next click.
* **The catalog owns its own copy.** Audio is copied under ``produced/`` because
  deleting a session removes everything rendered for it.
* **A produced take can still move** (SESS-18). Moving it takes its version back
  out of the song it went to (``release_take``) and stages it again, so it
  arrives in its new song the next time that song is produced.
"""
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi.concurrency import run_in_threadpool

from database import DatabaseManager
from src.api import radio_service
from src.api.routers import produce

logger = logging.getLogger("backend-api")

#: Recorded as the stem set's ``model``: nothing separated these, the band
#: recorded each channel apart.
SESSION_STEMS_MODEL = "session-channels"

#: The title a group gets when neither the producer nor the page supplied one.
UNTITLED = "Untitled song"


class NothingToProduce(Exception):
    """The group has no take that could become a version."""


def take_version_name(position: int, duration_seconds: float) -> str:
    """How a take reads in the versions list: its handle on the review page."""
    total = max(0, round(duration_seconds))
    return f"Take {position} ({total // 60}:{total % 60:02d})"


async def produce_group(
    db: DatabaseManager,
    session: Dict[str, Any],
    group: Dict[str, Any],
    title: Optional[str],
) -> Dict[str, Any]:
    """Bring a group into the catalog, returning its song id and what was added.

    ``title`` is the name the review page shows, which may be a guess made from
    the words; a name the producer set on the group always wins over it.
    """
    takes = await db.list_session_takes(session["id"])
    positions = {take["id"]: index + 1 for index, take in enumerate(takes)}
    members = [
        take for take in takes
        if take.get("group_id") == group["id"]
        and not take.get("excluded")
        and take.get("mix_path")
    ]
    pending = [take for take in members if take.get("song_version_id") is None]

    if group.get("song_id") is None and not pending:
        raise NothingToProduce("No take in this song has audio to bring in")

    name = (group.get("name") or title or "").strip()[:255] or UNTITLED
    song_id = await db.ensure_session_group_song(
        group["id"], name, session.get("recorded_on")
    )

    added: List[int] = []
    for take in pending:
        version_id = await _take_to_version(db, song_id, take, positions[take["id"]])
        if version_id is not None:
            added.append(version_id)

    logger.info(
        "Session %s group %s -> song %s: %d new versions",
        session["id"], group["id"], song_id, len(added),
    )
    return {"song_id": song_id, "added_versions": added}


async def release_take(db: DatabaseManager, take: Dict[str, Any]) -> None:
    """Take a produced take's version back out of its catalog song.

    The version's copied audio and channels go with it. If it was the song's
    default, the song is left with none rather than one chosen for the producer
    (SESS-15), which keeps it out of listeners' sight until they pick (SESS-20).
    The take's own audio in the session is never touched (SESS-14).
    """
    if take.get("song_version_id") is None:
        return
    released = await db.release_session_take_version(take["id"])
    if released is None:
        return

    for stem_set in released["stem_sets"]:
        await run_in_threadpool(
            shutil.rmtree,
            produce._stem_set_output_dir(stem_set["song_id"], stem_set["id"]),
            True,
        )
    version = released["version"]
    if version is None:
        return
    await run_in_threadpool(produce._remove_file, version["audio_path"])
    if version.get("is_published"):
        radio_service.clear_published_version_path(version["song_id"])
    logger.info(
        "Take %s released from song %s (version %s)",
        take["id"], version["song_id"], version["id"],
    )


async def _take_to_version(
    db: DatabaseManager, song_id: int, take: Dict[str, Any], position: int
) -> Optional[int]:
    """Copy one take's mix and channels into the catalog as a version.

    The copy's path is fixed by the take, so a run that failed partway and is
    produced again lands on the same version row (``add_song_version`` upserts
    on the path) rather than making a second (CAT-09).
    """
    source = Path(take["mix_path"])
    if not await run_in_threadpool(source.exists):
        logger.warning("Take %s has no mix on disk, skipping", take["id"])
        return None

    destination = (
        produce._produced_dir() / str(song_id) / "session"
        / f"take-{take['id']}{source.suffix or '.wav'}"
    )
    await run_in_threadpool(_copy, source, destination)

    duration = (take.get("end_seconds") or 0.0) - (take.get("start_seconds") or 0.0)
    version = await db.add_song_version(
        song_id,
        str(destination),
        label="session",
        metrics={
            "after": {"duration_seconds": duration},
            "session_take_id": take["id"],
        },
    )
    await db.rename_song_version(
        version["id"], take_version_name(position, duration)
    )
    # The stems' copies are warmed by _keep_stems; the full mix needs its own.
    produce.warm_version_preview_in_background(destination)

    parts = [
        {
            "name": stem["name"],
            "path": stem["path"],
            "display_name": stem.get("display_name"),
        }
        for stem in take.get("stems", [])
    ]
    await produce._keep_stems(
        song_id, version["id"], parts, "session", SESSION_STEMS_MODEL, db
    )

    await db.set_session_take_song_version(take["id"], version["id"])
    return version["id"]


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
