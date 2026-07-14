"""Production / audio-cleanup routes (issues #28, #30).

A path-safe delivery layer over the existing MCP audio-cleanup tools
(``analyze_and_recommend_processing``, ``auto_clean_recording``), surfaced in two
editor-gated producer surfaces:

- A quick **analyze → auto-clean** flow (issue #28) with per-step overrides and an
  intensity selector, used by the ``/produce`` page.
- An **audition + metrics-diff + version-and-publish** loop (issue #30) in the
  Admin producer area: a cleanup run produces a candidate the producer auditions,
  then approves (creating a new published *version* — the original is preserved
  and the new version is indexed through the same RAG audio seam the catalog uses,
  so every version is findable by audio similarity, and the radio/stream then
  serve the single published version) or discards.

In every case the browser passes a catalog ``song_id`` only — the source file and
a non-destructive output path are resolved on the backend, so container paths
never leave the server and a cleanup run can never overwrite the original catalog
audio or trigger a re-index of the original. Editor-gated, consistent with the
existing tools endpoint (issue #1).
"""
import time
from datetime import date, datetime
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
from src.api.region_tools import build_region_tool_args
from src.production import stem_separation
from database import DatabaseManager

router = APIRouter()

# Cleaned takes land in a dedicated subdirectory so they can never collide with a
# catalog file (named "{song_id}_*.mp3") that the RAG/radio paths index and serve,
# and are never mistaken for the original.
PRODUCED_SUBDIR = "produced"


class ProduceRequest(BaseModel):
    song_id: int
    aggressiveness: str = "moderate"
    steps_override: Optional[Dict[str, bool]] = None
    # When set, the clean starts from this version's audio (not the catalog
    # original), so an already-cleaned version can be re-cleaned with different
    # options into a new version (issue #49). The version must belong to the song.
    source_version_id: Optional[int] = None


class CleanRequest(BaseModel):
    song_id: int
    aggressiveness: str = "moderate"


class ApproveRequest(BaseModel):
    song_id: int
    candidate_path: str


class DiscardRequest(BaseModel):
    candidate_path: str


class RenameVersionRequest(BaseModel):
    name: str


class StemSeparateRequest(BaseModel):
    """Start a stem-separation job for a catalog song or one of its versions (issue #67)."""
    song_id: int
    # When set, separate this version's audio instead of the catalog original. The
    # version must belong to the song.
    source_version_id: Optional[int] = None


class StemAdjustment(BaseModel):
    """Per-stem mix control for a remix render (issue #67)."""
    gain: float = 1.0
    mute: bool = False


class StemRenderRequest(BaseModel):
    """Remix a stem set back down to a candidate audio file (issue #67).

    ``adjustments`` maps a stem name (vocals/drums/bass/guitar/other/...) to its
    gain/mute; unlisted stems play at unity gain, unmuted.
    """
    adjustments: Dict[str, StemAdjustment] = {}


class RegionToolRequest(BaseModel):
    """Run one v0.14.0 production tool over a selected time region (issue #70).

    The waveform editor sends the catalog ``song_id`` (optionally a
    ``source_version_id`` to process a specific version's audio), the friendly
    ``tool`` name, the region bounds, a wet/dry ``strength``, and any
    tool-specific ``params`` (target_bpm, key, eq_bands, ...). Preview and Apply
    share this shape — the only difference is whether the run becomes a version.
    """
    song_id: int
    source_version_id: Optional[int] = None
    tool: str
    start_s: Optional[float] = None
    end_s: Optional[float] = None
    strength: float = 1.0
    params: Dict[str, Any] = {}


class BatchStartRequest(BaseModel):
    """Start a catalog-wide auto-clean batch (issue #29).

    ``selection`` is "all" or "not_cleaned"; ``force_reclean_all`` reprocesses
    songs that already have a cleaned version even under "not_cleaned".
    """
    selection: str = "not_cleaned"
    aggressiveness: str = "moderate"
    force_reclean_all: bool = False


def _resolve_source_path(song_id: int) -> Path:
    """Locate the catalog audio file for a song, or 404."""
    audio_files = list(radio_service.AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    if not audio_files:
        raise HTTPException(
            status_code=404, detail=f"Audio file for song {song_id} not found"
        )
    return audio_files[0]


async def _resolve_clean_source_path(
    song_id: int, source_version_id: Optional[int], db: DatabaseManager
) -> Path:
    """Resolve the audio file a clean run should start from.

    With no ``source_version_id`` this is the catalog original (the existing
    behaviour). With one, it is that version's audio file — so an already-cleaned
    version can be re-cleaned with different options (issue #49). The version must
    belong to the song and its file must exist, else 404.
    """
    if source_version_id is None:
        return await run_in_threadpool(_resolve_source_path, song_id)

    version = await db.get_song_version(source_version_id)
    if version is None or version["song_id"] != song_id:
        raise HTTPException(
            status_code=404, detail="Source version not found for this song"
        )
    path = Path(version["audio_path"])
    if not await run_in_threadpool(path.exists):
        raise HTTPException(status_code=404, detail="Source version audio file missing")
    return path


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


def _remove_file(path: str) -> bool:
    """Delete a file if present. Synchronous (filesystem)."""
    target = Path(path)
    if target.exists():
        target.unlink()
        return True
    return False


def _file_size_bytes(path: str) -> Optional[int]:
    """Return a file's size in bytes, or None if it can't be read."""
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def _version_display_name(version: Dict[str, Any]) -> str:
    """The name shown in the versions list: producer-set name, else a label default."""
    name = version.get("name")
    if name:
        return name
    return "Original" if version.get("label") == "original" else "Cleaned"


def _version_view(version: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a song_versions row for the /produce versions list.

    Surfaces enough to tell versions apart: a display name, original/cleaned
    label, the published-default flag, produced-at timestamp, file size, and the
    steps/intensity/duration captured in metrics at publish time.
    """
    metrics = version.get("metrics") or {}
    after = metrics.get("after") if isinstance(metrics, dict) else None
    created_at = version.get("created_at")
    return {
        "id": version["id"],
        "name": _version_display_name(version),
        "label": version["label"],
        "is_published": version["is_published"],
        "steps_applied": metrics.get("steps_applied") if isinstance(metrics, dict) else None,
        "aggressiveness": metrics.get("aggressiveness") if isinstance(metrics, dict) else None,
        "duration_seconds": after.get("duration_seconds") if isinstance(after, dict) else None,
        "file_size_bytes": _file_size_bytes(version["audio_path"]),
        "metrics": version.get("metrics"),
        "created_at": created_at.isoformat() if created_at else None,
    }


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


def _iso_date(value: Any) -> Optional[str]:
    """Serialize a recorded-on date to an ISO ``YYYY-MM-DD`` string, or ``None``.

    asyncpg returns a ``date`` for a DATE column, but the catalog has rows where it
    is null or already a string, so normalize all three to a stable ISO string the
    frontend can format without hitting "Invalid Date" (issue #51).
    """
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def _catalog_song_view(song: Dict[str, Any], cleaned_ids: set) -> Dict[str, Any]:
    """Shape a catalog song row for the producer catalog table (issue #49).

    Surfaces the columns the table sorts/filters on plus a ``cleaned`` flag
    (whether the song has at least one non-original version). ``recorded_on`` is the
    bigflavorband.com recording date (issue #51), distinct from the system
    ``created_at``.
    """
    return {
        "id": song["id"],
        "title": song.get("title", "Unknown"),
        "genre": song.get("genre"),
        "tempo_bpm": song.get("tempo_bpm"),
        "duration_seconds": song.get("duration_seconds"),
        "recorded_on": _iso_date(song.get("recorded_on")),
        "cleaned": song["id"] in cleaned_ids,
    }


@router.get("/api/produce/songs")
async def list_catalog_songs(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """List catalog songs for the producer catalog table (issue #49).

    Returns each song's sortable/filterable columns plus a ``cleaned`` indicator,
    resolved with one bulk read of cleaned song ids (no N+1 per-song lookups).
    """
    songs = await db.get_all_songs()
    cleaned_ids = await db.get_song_ids_with_cleaned_versions()
    return {"songs": [_catalog_song_view(song, cleaned_ids) for song in songs]}


@router.get("/api/produce/songs/{song_id}")
async def get_catalog_song(
    song_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Return one catalog song for the per-song detail header (issue #49)."""
    song = await db.get_song(song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    cleaned_ids = await db.get_song_ids_with_cleaned_versions()
    return {"song": _catalog_song_view(song, cleaned_ids)}


# ---- issue #28: quick analyze + auto-clean ----

@router.post("/api/produce/analyze")
async def analyze_song(
    request: ProduceRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Analyze a catalog song and return detected issues + recommended steps.

    Analyzes the catalog original by default, or a chosen version's audio when
    ``source_version_id`` is set (issue #49).
    """
    source_path = await _resolve_clean_source_path(
        request.song_id, request.source_version_id, db
    )
    result = await agent.execute_tool(
        "analyze_and_recommend_processing", {"file_path": str(source_path)}
    )
    return {"result": result}


def _autoclean_dedup_key(
    cleanup_result: Dict[str, Any], source_version_id: Optional[int] = None
) -> str:
    """A stable key identifying an auto-clean candidate by its inputs (issue #47).

    Two auto-clean runs for the same song are "identical" when they cleaned the
    same source with the same set of steps at the same intensity, so the key is the
    source version (catalog original = none), the aggressiveness, and the sorted set
    of applied step names. A re-run producing the same key replaces the prior
    candidate instead of appending an indistinguishable duplicate; re-cleaning a
    *different* version with the same steps gets a distinct key (issue #49).
    """
    steps = sorted(
        {
            step.get("step")
            for step in cleanup_result.get("steps_applied", []) or []
            if step.get("step")
        }
    )
    aggressiveness = cleanup_result.get("aggressiveness") or ""
    source = "original" if source_version_id is None else f"v{source_version_id}"
    return f"{source}|{aggressiveness}|{','.join(steps)}"


async def save_autoclean_candidate(
    song_id: int,
    output_path: str,
    cleanup_result: Dict[str, Any],
    db: DatabaseManager,
    source_version_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Save a completed auto-clean run as a new candidate version (issue #47).

    Seeds the song's 'original' version, then records the rendered file as a
    *candidate* (label 'cleaned', NOT published — the song's default is left
    unchanged so the producer can promote it themselves). The version carries the
    steps/intensity/produced-at metadata the versions list renders. If an identical
    auto-clean candidate already exists for the song (same steps + intensity), its
    audio file and metrics are replaced in place rather than appending a duplicate.
    """
    source_path = await run_in_threadpool(_resolve_source_path, song_id)
    await db.ensure_original_version(song_id, str(source_path))

    after = await run_in_threadpool(_measure_audio, output_path)
    dedup_key = _autoclean_dedup_key(cleanup_result, source_version_id)
    metrics: Dict[str, Any] = {
        "steps_applied": cleanup_result.get("steps_applied", []),
        "aggressiveness": cleanup_result.get("aggressiveness"),
        "after": after,
        "produced_at": time.time(),
        "dedup_key": dedup_key,
    }

    existing = await db.find_cleaned_version_by_dedup_key(song_id, dedup_key)
    if existing is not None:
        # Identical re-run: swap the file in place and drop the superseded one,
        # keeping the row id and its publish state (never auto-promote here).
        if existing["audio_path"] != output_path:
            await run_in_threadpool(_remove_file, existing["audio_path"])
        version = await db.replace_song_version_audio(
            existing["id"], output_path, metrics
        )
        if version is None:
            version = await db.add_song_version(
                song_id, output_path, label="cleaned", metrics=metrics
            )
    else:
        version = await db.add_song_version(
            song_id, output_path, label="cleaned", metrics=metrics
        )

    return {"version_id": version["id"], "is_published": version["is_published"]}


@router.post("/api/produce/auto-clean")
async def auto_clean_song(
    request: ProduceRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Auto-clean a catalog song to a new derived file (original untouched).

    A quick one-shot clean: writes a cleaned file under produced/, saves it as a new
    candidate version of the song (NOT promoted to default — the producer chooses
    that), and returns the tool payload. Publishing a candidate as the default is
    the versions list's job (set-default), consistent with the audition flow.

    Cleans the catalog original by default, or re-cleans a chosen version's audio
    when ``source_version_id`` is set, producing a new version either way — the
    source version is never overwritten (issue #49).
    """
    source_path = await _resolve_clean_source_path(
        request.song_id, request.source_version_id, db
    )
    output_path = _build_output_path(request.song_id)

    parameters: Dict[str, Any] = {
        "file_path": str(source_path),
        "output_path": str(output_path),
        "aggressiveness": request.aggressiveness,
    }
    if request.steps_override is not None:
        parameters["steps_override"] = request.steps_override

    result = await agent.execute_tool("auto_clean_recording", parameters)

    # Only a successful run produces a file worth versioning; a failure must leave
    # the versions list and default untouched (issue #47).
    if result.get("status") == "success":
        version = await save_autoclean_candidate(
            request.song_id, str(output_path), result, db, request.source_version_id
        )
        return {"result": result, "version": version}

    return {"result": result}


# ---- issue #30: versions, audition, approve/discard ----

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
    # _version_view stats each file; run it off the event loop.
    views = await run_in_threadpool(lambda: [_version_view(v) for v in versions])
    return {"song_id": song_id, "versions": views}


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


@router.post("/api/produce/versions/{version_id}/default")
async def set_default_version(
    version_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Make a version the song's default (published) one.

    Reuses the transactional publish (exactly one published per song) and then
    refreshes the in-process published-path override so the radio playlist,
    search/preview, the /produce before/after preview, and downloads all flip to
    this version together — the same seam /approve uses.
    """
    version = await db.get_song_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    published = await db.publish_song_version(version["song_id"], version_id)
    if published is None:
        raise HTTPException(status_code=500, detail="Failed to set default version")
    radio_service.set_published_version_path(version["song_id"], version["audio_path"])
    return {
        "song_id": version["song_id"],
        "version_id": version_id,
        "is_published": True,
    }


@router.patch("/api/produce/versions/{version_id}")
async def rename_version(
    version_id: int,
    request: RenameVersionRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Rename a version (sets its producer-facing display name)."""
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name must not be empty")
    if len(name) > 120:
        raise HTTPException(status_code=400, detail="Name must be 120 characters or fewer")
    updated = await db.rename_song_version(version_id, name)
    if updated is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return {"version_id": version_id, "name": name}


@router.delete("/api/produce/versions/{version_id}")
async def delete_version(
    version_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Delete a version (its row and audio file).

    The song must always keep a resolvable default, so the song's last remaining
    version cannot be deleted, and deleting the current default promotes a
    fallback version (preferring the original) to default and refreshes the
    radio/stream override.
    """
    version = await db.get_song_version(version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    song_id = version["song_id"]
    if await db.count_song_versions(song_id) <= 1:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the song's only version",
        )

    fallback = None
    if version["is_published"]:
        fallback = await db.pick_fallback_version(song_id, version_id)
        if fallback is None:
            raise HTTPException(
                status_code=409,
                detail="Cannot delete the song's only version",
            )

    await db.delete_song_version(version_id)
    await run_in_threadpool(_remove_file, version["audio_path"])

    if fallback is not None:
        await db.publish_song_version(song_id, fallback["id"])
        radio_service.set_published_version_path(song_id, fallback["audio_path"])

    return {
        "deleted_version_id": version_id,
        "song_id": song_id,
        "new_default_version_id": fallback["id"] if fallback else None,
    }


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


async def clean_song_to_candidate(
    song_id: int,
    aggressiveness: str,
    agent: BigFlavorAgent,
    db: DatabaseManager,
) -> Dict[str, Any]:
    """Run auto-clean for one song into a non-destructive candidate file.

    Seeds the song's 'original' version, runs ``auto_clean_recording`` to a fresh
    file under produced/, and returns the candidate path plus a before/after diff.
    Shared by the single-track audition endpoint and the catalog batch runner
    (issue #29) so the cleanup behaviour can never diverge between them. Raises
    ValueError on a tool failure so callers can surface a reason.
    """
    source_path = await run_in_threadpool(_resolve_source_path, song_id)
    await db.ensure_original_version(song_id, str(source_path))
    output_path = _build_output_path(song_id)

    cleanup_result = await agent.execute_tool(
        "auto_clean_recording",
        {
            "file_path": str(source_path),
            "output_path": str(output_path),
            "aggressiveness": aggressiveness,
        },
    )
    if cleanup_result.get("status") != "success":
        raise ValueError(cleanup_result.get("error", "Auto-clean failed"))

    before = await run_in_threadpool(_measure_audio, str(source_path))
    after = await run_in_threadpool(_measure_audio, str(output_path))

    return {
        "song_id": song_id,
        "candidate_path": str(output_path),
        "diff": _build_diff(cleanup_result, before, after),
    }


async def publish_candidate_version(
    song_id: int,
    candidate_path: str,
    db: DatabaseManager,
    rag: SongRAGSystem,
) -> Dict[str, Any]:
    """Save a cleaned candidate as the song's new published version.

    Creates the version, indexes its audio embedding (same seam the catalog uses,
    so the new version is findable by audio similarity), marks it the single
    published version, and refreshes the radio/stream published-path override.
    Shared by the single-track approve endpoint and the batch runner (issue #29).
    Raises ValueError if the candidate is not a safe produced file or publish fails.
    """
    if not _is_within_produced(candidate_path):
        raise ValueError("Candidate must be a produced file")
    if not Path(candidate_path).exists():
        raise ValueError("Candidate file not found")

    # Capture the cleaned take's metrics so the version row records what was published.
    metrics = await run_in_threadpool(_measure_audio, candidate_path)
    version = await db.add_song_version(
        song_id,
        candidate_path,
        label="cleaned",
        metrics={"after": metrics} if metrics else None,
    )

    indexed = await rag.index_audio_file(candidate_path, song_id)

    published = await db.publish_song_version(song_id, version["id"])
    if published is None:
        raise ValueError("Failed to publish version")

    radio_service.set_published_version_path(song_id, candidate_path)

    return {
        "song_id": song_id,
        "version_id": version["id"],
        "is_published": True,
        "embedding_indexed": indexed,
    }


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
    try:
        return await clean_song_to_candidate(
            request.song_id, request.aggressiveness, agent, db
        )
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


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
    try:
        return await publish_candidate_version(
            request.song_id, request.candidate_path, db, rag
        )
    except ValueError as exc:
        # Missing resource -> 404, publish failure -> 500, other bad input -> 400.
        message = str(exc)
        if message == "Candidate file not found":
            status = 404
        elif message == "Failed to publish version":
            status = 500
        else:
            status = 400
        raise HTTPException(status_code=status, detail=message)


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


# ---- issue #29: catalog-wide auto-clean batch ----

@router.post("/api/produce/batch/start")
async def start_batch_clean(
    request: BatchStartRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    rag: SongRAGSystem = Depends(get_rag),
    _role: str = Depends(require_role("editor")),
):
    """Start a hands-off catalog-wide auto-clean batch.

    Selects "all" or "not_cleaned" songs, cleans each through the existing
    pipeline, and publishes each result as a new cleaned version (originals
    untouched). Returns immediately with the initial status; progress is polled
    from ``/api/produce/batch/status``. 409 if a batch is already running.
    """
    # Imported here to avoid a circular import (produce_batch imports this module).
    from src.api import produce_batch

    try:
        return produce_batch.manager.start(
            request.selection,
            request.aggressiveness,
            request.force_reclean_all,
            agent,
            db,
            rag,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/api/produce/batch/status")
async def batch_clean_status(
    _role: str = Depends(require_role("editor")),
):
    """Return the current/last catalog-clean batch's progress and per-track summary."""
    from src.api import produce_batch

    status = produce_batch.manager.status()
    if status is None:
        return {"status": "idle"}
    return status


# ---- issue #67: stem separation (separate / list / stream / remix) ----

STEMS_SUBDIR = "stems"


def _stem_set_output_dir(song_id: int, stem_set_id: int) -> Path:
    """Non-destructive output dir for one stem set: produced/{song_id}/stems/{set_id}/.

    Never overlaps a catalog original or a cleaned candidate — stems live in their
    own per-song/per-set subtree under produced/.
    """
    return _produced_dir() / str(song_id) / STEMS_SUBDIR / str(stem_set_id)


def _stem_set_view(stem_set: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a song_stem_sets row for the API (job status + provenance)."""
    created_at = stem_set.get("created_at")
    return {
        "id": stem_set["id"],
        "song_id": stem_set["song_id"],
        "source_version_id": stem_set["source_version_id"],
        "model": stem_set["model"],
        "status": stem_set["status"],
        "error": stem_set["error"],
        "created_at": created_at.isoformat() if created_at else None,
    }


@router.post("/api/produce/stems/separate")
async def separate_song_stems(
    request: StemSeparateRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Start a background stem-separation job for a song or one of its versions.

    Resolves the source (catalog original by default, or a specific version's
    audio when ``source_version_id`` is set), creates a queued stem set, and kicks
    off Demucs separation in the background. Returns immediately; the producer
    polls ``GET /api/produce/songs/{id}/stems`` for status. The original/version
    audio is only read — stems are written under produced/.
    """
    from src.api import stem_jobs

    source_path = await _resolve_clean_source_path(
        request.song_id, request.source_version_id, db
    )
    stem_set = await db.create_stem_set(
        request.song_id, stem_separation.DEFAULT_MODEL, request.source_version_id
    )
    output_dir = _stem_set_output_dir(request.song_id, stem_set["id"])
    stem_jobs.manager.start(
        stem_set["id"],
        str(source_path),
        str(output_dir),
        stem_separation.DEFAULT_MODEL,
        db,
    )
    return {"stem_set": _stem_set_view(stem_set)}


@router.get("/api/produce/songs/{song_id}/stems")
async def list_song_stems(
    song_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """List a song's stem sets (with job status) and each set's stems.

    A producer polls this to watch a separation job (queued/running/complete/
    failed) and, once complete, to fetch the per-stem ids for streaming/remix.
    """
    stem_sets = await db.list_stem_sets(song_id)
    views = []
    for stem_set in stem_sets:
        stems = await db.list_stems(stem_set["id"])
        view = _stem_set_view(stem_set)
        view["stems"] = [
            {"id": s["id"], "name": s["name"]} for s in stems
        ]
        views.append(view)
    return {"song_id": song_id, "stem_sets": views}


@router.get("/api/produce/stems/{stem_id}/audio")
async def stream_stem_audio(
    stem_id: int,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Stream a single stem's audio so each part can be auditioned independently."""
    stem = await db.get_stem(stem_id)
    if stem is None:
        raise HTTPException(status_code=404, detail="Stem not found")
    path = Path(stem["path"])
    if not await run_in_threadpool(path.exists):
        raise HTTPException(status_code=404, detail="Stem audio file missing")
    return FileResponse(path, headers={"Content-Disposition": "inline"})


@router.post("/api/produce/stems/{set_id}/render")
async def render_stem_remix(
    set_id: int,
    request: StemRenderRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Remix a completed stem set (per-stem gain/mute) into a produced candidate.

    Downmixes the set's stems into a fresh file under produced/, then returns its
    path as a candidate — the same shape the auto-clean/audition flow returns, so
    it enters the existing audition -> approve (``/api/produce/approve``) ->
    version flow unchanged. Nothing here touches the stems, originals, or versions.
    """
    stem_set = await db.get_stem_set(set_id)
    if stem_set is None:
        raise HTTPException(status_code=404, detail="Stem set not found")
    if stem_set["status"] != "complete":
        raise HTTPException(
            status_code=409, detail="Stem set separation is not complete"
        )

    stems = await db.list_stems(set_id)
    if not stems:
        raise HTTPException(status_code=404, detail="Stem set has no stems")

    output_path = _produced_dir() / f"{stem_set['song_id']}_remix_{int(time.time())}.wav"
    adjustments = {
        name: {"gain": adj.gain, "mute": adj.mute}
        for name, adj in request.adjustments.items()
    }
    try:
        await run_in_threadpool(
            stem_separation.remix_stems,
            [{"name": s["name"], "path": s["path"]} for s in stems],
            str(output_path),
            adjustments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "song_id": stem_set["song_id"],
        "stem_set_id": set_id,
        "candidate_path": str(output_path),
    }


# ---- issue #70: waveform region editor — region-scoped preview / apply ----


async def save_candidate_version(
    song_id: int,
    candidate_path: str,
    metrics: Dict[str, Any],
    db: DatabaseManager,
) -> Dict[str, Any]:
    """Record a produced file as a new unpublished candidate version (issue #70).

    Seeds the song's 'original' version, then adds the rendered file as a
    'cleaned' candidate — NOT published, so the song's default is untouched and
    the producer promotes it via the existing versions list (audition -> approve
    -> publish). Shared by region-apply and stem-mix apply so both enter that
    flow identically.
    """
    source_path = await run_in_threadpool(_resolve_source_path, song_id)
    await db.ensure_original_version(song_id, str(source_path))
    version = await db.add_song_version(
        song_id, candidate_path, label="cleaned", metrics=metrics
    )
    return {"version_id": version["id"], "is_published": version["is_published"]}


async def _run_region_tool(
    request: RegionToolRequest,
    output_path: Path,
    agent: BigFlavorAgent,
    db: DatabaseManager,
) -> Dict[str, Any]:
    """Resolve the source, map the tool, and run it into ``output_path``.

    Shared by preview and apply. Raises HTTPException (400 unknown tool, 502 tool
    failure) so both endpoints surface the same errors. Returns the tool payload.
    """
    source_path = await _resolve_clean_source_path(
        request.song_id, request.source_version_id, db
    )
    try:
        tool_name, args = build_region_tool_args(
            request.tool,
            request.start_s,
            request.end_s,
            request.strength,
            request.params,
            str(source_path),
            str(output_path),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = await agent.execute_tool(tool_name, args)
    if result.get("status") != "success":
        raise HTTPException(
            status_code=502,
            detail=result.get("error", f"{request.tool} failed"),
        )
    return result


@router.post("/api/produce/region/preview")
async def preview_region(
    request: RegionToolRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Process only the selected region and return a produced file to audition.

    Non-destructive: writes a preview file under produced/ (streamable via
    ``GET /api/produce/preview``) and creates **no** song version, so a producer
    can A/B the result against the original before committing (issue #70).
    """
    output_path = _produced_dir() / f"{request.song_id}_preview_{int(time.time())}.wav"
    result = await _run_region_tool(request, output_path, agent, db)
    return {
        "status": "success",
        "tool": request.tool,
        "candidate_path": str(output_path),
        "result": result,
    }


@router.post("/api/produce/region/apply")
async def apply_region(
    request: RegionToolRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Apply a region tool and save the result as a new candidate version.

    Same processing as preview, but the produced file becomes an unpublished
    candidate version that enters the existing audition/approve/publish flow —
    that flow is unchanged; this is only a new entry point into it (issue #70).
    """
    output_path = _build_output_path(request.song_id)
    result = await _run_region_tool(request, output_path, agent, db)

    after = await run_in_threadpool(_measure_audio, str(output_path))
    metrics = {
        "steps_applied": [{"step": request.tool}],
        "region": {"start_s": request.start_s, "end_s": request.end_s},
        "strength": request.strength,
        "after": after,
        "produced_at": time.time(),
    }
    version = await save_candidate_version(
        request.song_id, str(output_path), metrics, db
    )
    return {"status": "success", "result": result, "version": version}


def _detect_song_beats(path: str) -> list:
    """Detect beat times (seconds) for a source file, reusing #69's detector.

    Synchronous/CPU-bound (librosa) — callers run it off the event loop.
    """
    import librosa
    from src.production.big_flavor_mcp import _detect_beats

    y, sr = librosa.load(path, sr=22050, mono=True)
    _tempo, beat_times, _conf = _detect_beats(y, sr)
    return [round(float(t), 3) for t in beat_times]


@router.get("/api/produce/songs/{song_id}/beats")
async def get_song_beats(
    song_id: int,
    source_version_id: Optional[int] = None,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Return beat times for waveform beat markers (issue #70, reuses #69).

    Degrades gracefully: on any detection error returns an empty list rather than
    failing, so the editor stays usable when beats can't be found.
    """
    source_path = await _resolve_clean_source_path(song_id, source_version_id, db)
    try:
        beats = await run_in_threadpool(_detect_song_beats, str(source_path))
    except Exception:
        beats = []
    return {"song_id": song_id, "beats": beats}


@router.post("/api/produce/stems/{set_id}/apply")
async def apply_stem_remix(
    set_id: int,
    request: StemRenderRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """Remix a stem set (per-stem gain/mute) into a new candidate version.

    The stem-mixer's entry point into the versioning flow: downmixes the set with
    the given adjustments, then saves the result as an unpublished candidate
    version (same as region-apply). Nothing here touches the stems or originals
    (issue #70).
    """
    stem_set = await db.get_stem_set(set_id)
    if stem_set is None:
        raise HTTPException(status_code=404, detail="Stem set not found")
    if stem_set["status"] != "complete":
        raise HTTPException(
            status_code=409, detail="Stem set separation is not complete"
        )

    stems = await db.list_stems(set_id)
    if not stems:
        raise HTTPException(status_code=404, detail="Stem set has no stems")

    output_path = _produced_dir() / f"{stem_set['song_id']}_remix_{int(time.time())}.wav"
    adjustments = {
        name: {"gain": adj.gain, "mute": adj.mute}
        for name, adj in request.adjustments.items()
    }
    try:
        await run_in_threadpool(
            stem_separation.remix_stems,
            [{"name": s["name"], "path": s["path"]} for s in stems],
            str(output_path),
            adjustments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    after = await run_in_threadpool(_measure_audio, str(output_path))
    metrics = {
        "steps_applied": [{"step": "stem_remix"}],
        "stem_set_id": set_id,
        "after": after,
        "produced_at": time.time(),
    }
    version = await save_candidate_version(
        stem_set["song_id"], str(output_path), metrics, db
    )
    return {
        "song_id": stem_set["song_id"],
        "stem_set_id": set_id,
        "candidate_path": str(output_path),
        "version": version,
    }
