"""Production / audio-cleanup audition routes (issue #30).

The audition + metrics-diff + version-and-publish loop around the existing MCP
``auto_clean_recording`` tool, surfaced in the Admin producer area. The browser
passes a catalog ``song_id`` only — source and (non-destructive) output paths are
resolved on the backend, so container paths never leave the server and a cleanup
run can never overwrite the original catalog audio.

Approving a cleaned take creates a new *version* of the song (the original is
preserved), indexes that version's audio embedding through the same RAG seam the
catalog uses (so every version is findable by audio similarity), and marks it the
single published version that the radio/stream then serve.

Editor-gated, consistent with the existing tools endpoint (issue #1).
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from src.auth import require_role
from src.api.dependencies import get_agent, get_db, get_rag
from src.api import radio_service
from database import DatabaseManager

router = APIRouter()

# Cleaned takes land in a dedicated subdirectory so they can never collide with a
# catalog file (named "{song_id}_*.mp3") and are never mistaken for the original.
PRODUCED_SUBDIR = "produced"


class CleanRequest(BaseModel):
    song_id: int
    aggressiveness: str = "moderate"


class ApproveRequest(BaseModel):
    song_id: int
    candidate_path: str


class DiscardRequest(BaseModel):
    candidate_path: str


def _resolve_source_path(song_id: int) -> Path:
    """Locate the catalog audio file for a song, or 404."""
    audio_files = list(radio_service.AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    if not audio_files:
        raise HTTPException(
            status_code=404, detail=f"Audio file for song {song_id} not found"
        )
    return audio_files[0]


def _produced_dir() -> Path:
    produced_dir = radio_service.AUDIO_LIBRARY_DIR / PRODUCED_SUBDIR
    produced_dir.mkdir(parents=True, exist_ok=True)
    return produced_dir


def _build_output_path(song_id: int) -> Path:
    """Compute a non-destructive output path under produced/.

    Never returns the catalog source path, so a cleanup run cannot overwrite the
    original audio in place.
    """
    return _produced_dir() / f"{song_id}_cleaned_{int(time.time())}.wav"


def _is_within_produced(candidate_path: str) -> bool:
    """Guard: a candidate to approve/discard must live under produced/.

    Prevents a caller from pointing approve/discard at an arbitrary path (e.g. a
    catalog original) and having it published or deleted.
    """
    try:
        resolved = Path(candidate_path).resolve()
        produced = _produced_dir().resolve()
        return produced in resolved.parents
    except (OSError, ValueError):
        return False


def _measure_audio(file_path: str) -> Optional[Dict[str, Any]]:
    """Compute before/after diff metrics for one file (LUFS estimate, peak, duration).

    Synchronous/CPU-bound (librosa) — callers run it off the event loop. Returns
    None if the file can't be read so a missing measurement never fails the flow.
    The LUFS figure is the same simplified RMS-based estimate the MCP mastering
    path uses, kept consistent so before/after numbers are comparable.
    """
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(file_path, sr=None, mono=True)
        if y.size == 0:
            return None
        peak = float(np.max(np.abs(y)))
        rms = float(np.sqrt(np.mean(y ** 2)))
        peak_db = round(20.0 * float(np.log10(peak)), 2) if peak > 0 else None
        lufs_estimate = round(20.0 * float(np.log10(rms)) - 15.0, 2) if rms > 0 else None
        return {
            "duration_seconds": round(float(librosa.get_duration(y=y, sr=sr)), 2),
            "peak_db": peak_db,
            "integrated_lufs_estimate": lufs_estimate,
        }
    except Exception:
        return None


def _noise_reduction_db(cleanup_result: Dict[str, Any]) -> Optional[float]:
    """Pull the applied noise-reduction amount (dB) out of the cleanup payload."""
    for step in cleanup_result.get("steps_applied", []) or []:
        if step.get("step") == "noise_reduction":
            return step.get("reduction_db")
    return None


def _build_diff(
    cleanup_result: Dict[str, Any],
    before: Optional[Dict[str, Any]],
    after: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Assemble the before/after metrics diff the producer surface renders."""
    return {
        "before": before,
        "after": after,
        "steps_applied": cleanup_result.get("steps_applied", []),
        "aggressiveness": cleanup_result.get("aggressiveness"),
        "noise_reduction_db": _noise_reduction_db(cleanup_result),
        "analysis_summary": cleanup_result.get("analysis_summary"),
    }


@router.get("/api/produce/songs")
async def list_catalog_songs(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """List catalog songs (id + title) for the producer song picker."""
    songs = await db.get_all_songs()
    return {
        "songs": [
            {"id": song["id"], "title": song.get("title", "Unknown")}
            for song in songs
        ]
    }


@router.get("/api/produce/songs/{song_id}/versions")
async def list_versions(
    song_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """List a song's versions, seeding the 'original' version on first access."""
    source_path = await run_in_threadpool(_resolve_source_path, song_id)
    await db.ensure_original_version(song_id, str(source_path))
    versions = await db.list_song_versions(song_id)
    return {
        "song_id": song_id,
        "versions": [
            {
                "id": v["id"],
                "label": v["label"],
                "is_published": v["is_published"],
                "metrics": v["metrics"],
                "created_at": v["created_at"].isoformat() if v["created_at"] else None,
            }
            for v in versions
        ],
    }


@router.get("/api/produce/versions/{version_id}/audio")
async def stream_version_audio(
    version_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Stream a single version's audio so original and cleaned can be auditioned."""
    version = await db.get_song_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    path = Path(version["audio_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Version audio file missing")
    return FileResponse(path, headers={"Content-Disposition": "inline"})


@router.get("/api/produce/preview")
async def stream_candidate_preview(
    path: str,
    _role: str = Depends(require_role("editor")),
):
    """Stream a not-yet-approved cleaned candidate so it can be auditioned.

    Restricted to files under produced/ so it can never serve an arbitrary path.
    """
    if not _is_within_produced(path):
        raise HTTPException(status_code=400, detail="Path must be a produced file")
    candidate = Path(path)
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Candidate file not found")
    return FileResponse(candidate, headers={"Content-Disposition": "inline"})


@router.post("/api/produce/clean")
async def clean_song(
    request: CleanRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Auto-clean a song into a candidate file and return the before/after diff.

    Does not change any version — it produces a candidate the producer auditions,
    then approves or discards.
    """
    source_path = await run_in_threadpool(_resolve_source_path, request.song_id)
    await db.ensure_original_version(request.song_id, str(source_path))
    output_path = _build_output_path(request.song_id)

    cleanup_result = await agent.execute_tool(
        "auto_clean_recording",
        {
            "file_path": str(source_path),
            "output_path": str(output_path),
            "aggressiveness": request.aggressiveness,
        },
    )
    if cleanup_result.get("status") != "success":
        raise HTTPException(
            status_code=502,
            detail=cleanup_result.get("error", "Auto-clean failed"),
        )

    before = await run_in_threadpool(_measure_audio, str(source_path))
    after = await run_in_threadpool(_measure_audio, str(output_path))

    return {
        "song_id": request.song_id,
        "candidate_path": str(output_path),
        "diff": _build_diff(cleanup_result, before, after),
    }


@router.post("/api/produce/approve")
async def approve_version(
    request: ApproveRequest,
    db: DatabaseManager = Depends(get_db),
    rag: SongRAGSystem = Depends(get_rag),
    _role: str = Depends(require_role("editor")),
):
    """Save the cleaned candidate as a new published version of the song.

    Creates the version, indexes its audio embedding (same seam the catalog uses,
    so the new version is findable by audio similarity), marks it the single
    published version, and refreshes the radio/stream published-path override.
    """
    if not _is_within_produced(request.candidate_path):
        raise HTTPException(status_code=400, detail="Candidate must be a produced file")
    if not Path(request.candidate_path).exists():
        raise HTTPException(status_code=404, detail="Candidate file not found")

    # Capture the cleaned take's metrics so the version row records what was published.
    metrics = await run_in_threadpool(_measure_audio, request.candidate_path)
    version = await db.add_song_version(
        request.song_id,
        request.candidate_path,
        label="cleaned",
        metrics={"after": metrics} if metrics else None,
    )

    indexed = await rag.index_audio_file(request.candidate_path, request.song_id)

    published = await db.publish_song_version(request.song_id, version["id"])
    if published is None:
        raise HTTPException(status_code=500, detail="Failed to publish version")

    radio_service.set_published_version_path(request.song_id, request.candidate_path)

    return {
        "song_id": request.song_id,
        "version_id": version["id"],
        "is_published": True,
        "embedding_indexed": indexed,
    }


@router.post("/api/produce/discard")
async def discard_candidate(
    request: DiscardRequest,
    _role: str = Depends(require_role("editor")),
):
    """Discard a cleaned candidate file, leaving all existing versions unchanged."""
    if not _is_within_produced(request.candidate_path):
        raise HTTPException(status_code=400, detail="Candidate must be a produced file")
    removed = await run_in_threadpool(_remove_file, request.candidate_path)
    return {"discarded": removed, "candidate_path": request.candidate_path}


def _remove_file(path: str) -> bool:
    """Delete a file if present. Synchronous (filesystem)."""
    target = Path(path)
    if target.exists():
        target.unlink()
        return True
    return False
