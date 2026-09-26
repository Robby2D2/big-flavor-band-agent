"""Recording-session import routes.

The band records a whole rehearsal in Reaper and uploads the project as a zip;
these routes take it, find the songs inside, and serve what was found for review.

Two things shape the surface:

* **Upload is chunked.** A session is multiple gigabytes — the sample was 2 GB —
  and nginx caps a body at 100 MB with a 60s read timeout. So the browser slices
  the file and PUTs the pieces, which also makes a dropped connection resumable
  instead of fatal. ``POST /sessions`` opens one, ``PUT .../chunk`` appends, and
  ``POST .../complete`` starts the scan.
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

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import DatabaseManager
from src.api.dependencies import get_db
from src.api.session_jobs import manager as session_manager, session_dir
from src.auth import require_role
from src.production import audio_preview, waveform_peaks

logger = logging.getLogger("backend-api")

router = APIRouter()

#: A session's name and date come from the zip's own name, which is how the band
#: already labels them: "20260501 May the Farts Be With You".
_DATED_NAME = re.compile(r"^\s*(?P<date>\d{8})[\s_-]+(?P<name>.+?)\s*$")

#: Google Drive appends its own export suffix when it zips a folder.
_DRIVE_SUFFIX = re.compile(r"-\d{8}T\d{6}Z-\d+-\d+$")


class SessionCreate(BaseModel):
    filename: str


class TakeUpdate(BaseModel):
    excluded: bool


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

    target = _zip_path(session_id)
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

    target = _zip_path(session_id)
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

    The band names its project folders ``20260501 May the Farts Be With You``, so
    the date is already there. A zip made by Google Drive carries an export
    suffix, which is stripped first.
    """
    stem = Path(filename).stem
    stem = _DRIVE_SUFFIX.sub("", stem)
    match = _DATED_NAME.match(stem)
    if not match:
        return (stem or "Recording session"), None
    raw = match.group("date")
    return match.group("name"), f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"


def _zip_path(session_id: int) -> Path:
    return session_dir(session_id) / "upload.zip"


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
