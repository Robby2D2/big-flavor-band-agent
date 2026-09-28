"""Recording-session import routes.

The band records a whole rehearsal in Reaper and uploads the project as a zip;
these routes take it, find the songs inside, and serve what was found for review.

Two things shape the surface:

* **Upload is chunked.** A session is multiple gigabytes — the sample was 2 GB —
  and nginx caps a body at 100 MB with a 60s read timeout. So the browser slices
  the file and PUTs the pieces, which also makes a dropped connection resumable
  instead of fatal. ``POST /sessions`` opens one, ``PUT .../chunk`` appends, and
  ``POST .../complete`` starts the scan.
* **Or it comes from Drive.** The band's Reaper projects already sit in a shared
  Google Drive folder, so ``/sessions/drive`` lists those folders and imports one
  by downloading it server-side — no zip, no browser transfer (``drive_source``).
* **Audio is served the way the stem console's is** — a cached drawing envelope
  for the waveform and a compressed copy for playback, never the 24-bit source,
  because a take is minutes of multitrack and the browser only needs to draw it
  and play it.

Nothing here writes to the catalog. Detection is fallible, so a take stays staged
until a human confirms it; importing one into ``songs``/``song_versions`` is a
later step with its own routes.
"""
import logging
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import DatabaseManager
from src.api.dependencies import get_db
from src.api.session_jobs import (
    group_session_takes,
    manager as session_manager,
    session_dir,
    upload_zip_path,
)
from src.auth import require_role
from src.production import audio_preview, drive_source, waveform_peaks

logger = logging.getLogger("backend-api")

router = APIRouter()

#: A session's name and date come from the zip's own name, which is how the band
#: already labels them: "20260501 May the Farts Be With You".
_DATED_NAME = re.compile(r"^\s*(?P<date>\d{8})[\s_-]+(?P<name>.+?)\s*$")

#: Google Drive appends its own export suffix when it zips a folder.
_DRIVE_SUFFIX = re.compile(r"-\d{8}T\d{6}Z-\d+-\d+$")


class SessionCreate(BaseModel):
    filename: str


class DriveImport(BaseModel):
    folder_id: str


class TakeUpdate(BaseModel):
    excluded: bool


class GroupUpdate(BaseModel):
    """A producer's corrections to a guessed group.

    Both fields are read through ``model_fields_set``, so clearing one — a blank
    name back to the guess, or un-choosing a keeper — is distinguishable from not
    touching it.
    """

    name: Optional[str] = None
    keeper_take_id: Optional[int] = None


@router.post("/api/produce/sessions")
async def create_session(
    body: SessionCreate,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Open a session and return where to send its chunks."""
    name, recorded_on = parse_session_filename(body.filename)
    session = await db.create_recording_session(
        name=name, source_filename=body.filename, recorded_on=recorded_on
    )
    directory = session_dir(session["id"])
    await run_in_threadpool(lambda: directory.mkdir(parents=True, exist_ok=True))
    return _session_payload(session)


@router.get("/api/produce/sessions/drive")
async def list_drive_sessions(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """The session folders on the band's Drive, marked with any import of each.

    A folder counts as imported when a session came from it, or — for the
    sessions uploaded as zips before Drive import existed — when a session has
    its name and date, so a night already scanned is not fetched again by
    accident.

    Declared before ``/sessions/{session_id}`` so "drive" is not read as an id.
    """
    if not drive_source.configured():
        return {"configured": False, "folders": []}

    found = await _drive_sessions()
    rows = await db.list_recording_sessions()
    by_folder = {row["drive_folder_id"]: row for row in rows if row.get("drive_folder_id")}
    by_night = {
        _night_key(row["name"], row.get("recorded_on")): row
        for row in rows
        if not row.get("drive_folder_id")
    }
    payload = []
    for drive_session in found:
        folder = drive_session.folder
        name, recorded_on = parse_session_name(folder.name)
        session = by_folder.get(folder.id) or by_night.get(_night_key(name, recorded_on))
        payload.append({
            "id": folder.id,
            "folder_name": folder.name,
            "location": " / ".join(drive_session.location) or None,
            "name": name,
            "recorded_on": recorded_on,
            "session_id": session["id"] if session else None,
            "session_status": session["status"] if session else None,
        })
    return {"configured": True, "folders": payload}


@router.post("/api/produce/sessions/drive")
async def import_drive_session(
    body: DriveImport,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Open a session from a Drive folder and start downloading and scanning it."""
    if not drive_source.configured():
        raise HTTPException(status_code=404, detail="Google Drive import is not set up")

    # Only a session folder under the configured root, never an arbitrary id.
    folder = next(
        (
            found.folder
            for found in await _drive_sessions()
            if found.folder.id == body.folder_id
        ),
        None,
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="No such session folder on Drive")

    name, recorded_on = parse_session_name(folder.name)
    try:
        session = await db.create_recording_session(
            name=name,
            source_filename=folder.name,
            recorded_on=recorded_on,
            status="running",
            drive_folder_id=folder.id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409, detail="This folder has already been imported"
        )

    await run_in_threadpool(
        lambda: session_dir(session["id"]).mkdir(parents=True, exist_ok=True)
    )
    session_manager.start_from_drive(session["id"], folder.id, db)
    return _session_payload(session)


@router.put("/api/produce/sessions/{session_id}/chunk")
async def upload_chunk(
    session_id: int,
    request: Request,
    offset: int = 0,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Append one chunk of the upload.

    ``offset`` is where the chunk belongs in the file, so a retried or resumed
    upload rewrites the same bytes rather than appending them twice.
    """
    session = await db.get_recording_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] != "uploading":
        raise HTTPException(
            status_code=409, detail=f"Session is {session['status']}, not uploading"
        )

    target = upload_zip_path(session_id)
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty chunk")

    def write() -> int:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "r+b" if target.exists() else "wb") as handle:
            handle.seek(offset)
            handle.write(body)
        return target.stat().st_size

    size = await run_in_threadpool(write)
    return {"received": len(body), "size": size}


@router.post("/api/produce/sessions/{session_id}/complete")
async def complete_upload(
    session_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Finish the upload and start the scan."""
    session = await db.get_recording_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_manager.is_running(session_id):
        return _session_payload(session)

    target = upload_zip_path(session_id)
    if not target.exists() or target.stat().st_size == 0:
        raise HTTPException(status_code=400, detail="No upload received")

    started = await db.set_recording_session_status(
        session_id, "running", stage="unpacking", progress=0
    )
    session_manager.start(session_id, str(target), db)
    return _session_payload(started or session)


@router.get("/api/produce/sessions")
async def list_sessions(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Every uploaded session, newest first."""
    sessions = await db.list_recording_sessions()
    return {"sessions": [_session_payload(row) for row in sessions]}


@router.get("/api/produce/sessions/{session_id}")
async def get_session(
    session_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """One session with its channels and the takes found in it."""
    session = await db.get_recording_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    tracks = await db.list_session_tracks(session_id)
    takes = await db.list_session_takes(session_id)
    payload = _session_payload(session)
    payload["tracks"] = [_track_payload(row) for row in tracks]
    payload["takes"] = [_take_payload(row) for row in takes]
    payload["groups"] = [
        _group_payload(row) for row in await db.list_session_take_groups(session_id)
    ]
    return payload


@router.delete("/api/produce/sessions/{session_id}")
async def delete_session(
    session_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Delete a session and everything unpacked or rendered for it."""
    session = await db.get_recording_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete_recording_session(session_id)
    await run_in_threadpool(shutil.rmtree, session_dir(session_id), True)
    return {"deleted": session_id}


@router.patch("/api/produce/sessions/takes/{take_id}")
async def update_take(
    take_id: int,
    body: TakeUpdate,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Set a take aside, or bring it back. The audio is never deleted."""
    if await db.get_session_take(take_id) is None:
        raise HTTPException(status_code=404, detail="Take not found")
    updated = await db.set_session_take_excluded(take_id, body.excluded)
    return _take_payload(dict(updated or {}, stems=[]))


@router.post("/api/produce/sessions/takes/{take_id}/separate")
async def separate_take(
    take_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Pull a take out of the group it was guessed into, so it stands on its own.

    Grouping is a guess (SESS-05); this is how a producer overrules one. The take
    keeps everything else — its audio, its channels, its discard state.
    """
    take = await db.get_session_take(take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="Take not found")
    updated = await db.set_session_take_group_id(take_id, None)
    return _take_payload(dict(updated or take, stems=[]))


@router.patch("/api/produce/sessions/groups/{group_id}")
async def update_group(
    group_id: int,
    body: GroupUpdate,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Rename a group, or choose which of its takes is the keeper."""
    group = await db.get_session_take_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    fields = body.model_fields_set

    if "name" in fields:
        name = (body.name or "").strip()
        group = await db.set_session_take_group_name(group_id, name or None)

    if "keeper_take_id" in fields:
        if body.keeper_take_id is not None:
            take = await db.get_session_take(body.keeper_take_id)
            if take is None or take.get("group_id") != group_id:
                raise HTTPException(
                    status_code=400, detail="That take is not in this group"
                )
        group = await db.set_session_take_group_keeper(group_id, body.keeper_take_id)

    return _group_payload(group or {})


@router.post("/api/produce/sessions/{session_id}/regroup")
async def regroup_session(
    session_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """Guess this session's song groups again from what was transcribed.

    Grouping runs at the end of a scan, but it reads only transcripts, so a
    session scanned before it existed can be grouped without re-uploading
    gigabytes of audio. It discards the names and keepers already set, which is
    why nothing but an explicit request triggers it.
    """
    session = await db.get_recording_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if session_manager.is_running(session_id):
        raise HTTPException(status_code=409, detail="This session is still scanning")

    groups = await group_session_takes(db, session_id)
    return {"session_id": session_id, "groups": groups}


@router.get("/api/produce/sessions/takes/{take_id}/peaks")
async def take_peaks(
    take_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """The take mix's drawing envelope, computed on demand if not yet cached."""
    take = await db.get_session_take(take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="Take not found")
    return await _peaks_for(
        take, db.set_session_take_waveform_peaks, take_id, take.get("mix_path")
    )


@router.get("/api/produce/sessions/takes/{take_id}/preview")
async def take_preview(
    take_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> FileResponse:
    """A compressed copy of the take mix, for browser playback only."""
    take = await db.get_session_take(take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="Take not found")
    return await _preview_for(take.get("mix_path"))


@router.get("/api/produce/sessions/stems/{stem_id}/peaks")
async def stem_peaks(
    stem_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> Dict[str, Any]:
    """One take stem's drawing envelope."""
    stem = await db.get_session_take_stem(stem_id)
    if stem is None:
        raise HTTPException(status_code=404, detail="Stem not found")
    return await _peaks_for(
        stem, db.set_session_take_stem_waveform_peaks, stem_id, stem.get("path")
    )


@router.get("/api/produce/sessions/stems/{stem_id}/preview")
async def stem_preview(
    stem_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
) -> FileResponse:
    """A compressed copy of one take stem, for browser playback only."""
    stem = await db.get_session_take_stem(stem_id)
    if stem is None:
        raise HTTPException(status_code=404, detail="Stem not found")
    return await _preview_for(stem.get("path"))


# --- helpers --------------------------------------------------------------

def parse_session_filename(filename: str) -> tuple[str, Optional[str]]:
    """Read a session's name and date out of the uploaded file's name.

    A zip made by Google Drive carries an export suffix, which is stripped
    first.
    """
    return parse_session_name(_DRIVE_SUFFIX.sub("", Path(filename).stem))


def parse_session_name(folder_name: str) -> tuple[str, Optional[str]]:
    """Read a session's name and date out of its project folder's name.

    The band names its project folders ``20260501 May the Farts Be With You``, so
    the date is already there. Taken as-is — no extension stripping — because a
    folder name may contain a dot ("Vol. 2").
    """
    match = _DATED_NAME.match(folder_name)
    if not match:
        return (folder_name.strip() or "Recording session"), None
    raw = match.group("date")
    return match.group("name"), f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


async def _drive_sessions() -> List[drive_source.DriveSession]:
    """Find the session folders on Drive, surfacing Drive's own error text."""

    def fetch() -> List[drive_source.DriveSession]:
        client = drive_source.DriveClient()
        return drive_source.find_sessions(client, drive_source.root_folder_id())

    try:
        return await run_in_threadpool(fetch)
    except drive_source.DriveError as exc:
        logger.warning("Google Drive listing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))



def _night_key(name: str, recorded_on: Any) -> tuple[str, Optional[str]]:
    """A session's identity by what the band called the night and its date."""
    if recorded_on is not None and not isinstance(recorded_on, str):
        recorded_on = recorded_on.isoformat()
    return (" ".join(name.split()).casefold(), recorded_on)


def _session_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "recorded_on": row["recorded_on"].isoformat() if row.get("recorded_on") else None,
        "status": row["status"],
        "stage": row.get("stage"),
        "progress": row.get("progress", 0),
        "error": row.get("error"),
        "rec_passes": list(row.get("rec_passes") or []),
        "sample_rate": row.get("sample_rate"),
        "duration_seconds": row.get("duration_seconds"),
        "take_count": row.get("take_count"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _track_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "role": row["role"],
        "rec_pass": row.get("rec_pass"),
        "position_seconds": row.get("position_seconds"),
        "peak_db": row.get("peak_db"),
        "is_dead": row.get("is_dead", False),
    }


def _take_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    start = row.get("start_seconds") or 0.0
    end = row.get("end_seconds") or 0.0
    return {
        "id": row["id"],
        "group_id": row.get("group_id"),
        "rec_pass": row.get("rec_pass"),
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": end - start,
        "transcript": row.get("transcript"),
        "excluded": row.get("excluded", False),
        "has_audio": bool(row.get("mix_path")),
        "stems": [
            {
                "id": stem["id"],
                "name": stem["name"],
                "display_name": stem.get("display_name"),
                "peak_db": stem.get("peak_db"),
            }
            for stem in row.get("stems", [])
        ],
    }


def _group_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "keeper_take_id": row.get("keeper_take_id"),
    }


async def _peaks_for(
    row: Dict[str, Any], setter, row_id: int, audio_path: Optional[str]
) -> Dict[str, Any]:
    """Serve a cached envelope, computing and caching it on a miss.

    Wrapped as ``{"peaks": ...}`` and version-guarded through the same helpers
    the stem and version routes use, so ``fetchPeaks`` on the client reads a
    session take exactly as it reads a stem.
    """
    cached = waveform_peaks.usable_cached_peaks(row.get("waveform_peaks"))
    if cached is not None:
        return {"peaks": cached}

    if not audio_path or not await run_in_threadpool(Path(audio_path).exists):
        raise HTTPException(status_code=404, detail="No audio for this row")

    peaks = await run_in_threadpool(waveform_peaks.compute_peaks, audio_path)
    await setter(row_id, peaks)
    return {"peaks": peaks}


async def _preview_for(audio_path: Optional[str]) -> FileResponse:
    """Serve a compressed playback copy, building it on a miss."""
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(status_code=404, detail="No audio for this row")

    source = Path(audio_path)
    preview = audio_preview.stem_preview_path(source)
    if not preview.exists():
        await run_in_threadpool(
            audio_preview.build_preview, str(source), str(preview)
        )
    return FileResponse(
        str(preview),
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
