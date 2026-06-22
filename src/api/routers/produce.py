"""Production UI routes (issue #28).

A thin, path-safe delivery layer over the existing MCP audio-cleanup tools
(`analyze_and_recommend_processing`, `auto_clean_recording`). The browser passes
a catalog ``song_id`` only — the audio file path and a non-destructive output
path are resolved here on the backend, so container paths never leave the server
and an auto-clean run can never overwrite the original catalog audio or trigger a
re-index. Editor-gated, consistent with the existing tools endpoint (issue #1).
"""
import time
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.agent.big_flavor_agent import BigFlavorAgent
from src.auth import require_role
from src.api.dependencies import get_agent, get_db
from src.api import radio_service
from database import DatabaseManager

router = APIRouter()

# Cleaned output lands in a dedicated subdirectory so it can never collide with a
# catalog file (named "{song_id}_*.mp3") that the RAG/radio paths index and serve.
PRODUCED_SUBDIR = "produced"


class ProduceRequest(BaseModel):
    song_id: int
    aggressiveness: str = "moderate"
    steps_override: Optional[Dict[str, bool]] = None


def _resolve_source_path(song_id: int) -> Path:
    """Locate the catalog audio file for a song, or 404."""
    audio_path = radio_service._find_audio_file(song_id)
    if audio_path is None:
        raise HTTPException(
            status_code=404, detail=f"Audio file for song {song_id} not found"
        )
    return audio_path


def _build_output_path(song_id: int) -> Path:
    """Compute a non-destructive output path under the produced/ subdir.

    Never returns the catalog source path, so an auto-clean run cannot overwrite
    the original audio in place.
    """
    produced_dir = radio_service.AUDIO_LIBRARY_DIR / PRODUCED_SUBDIR
    produced_dir.mkdir(parents=True, exist_ok=True)
    return produced_dir / f"{song_id}_cleaned_{int(time.time())}.wav"


@router.get("/api/produce/songs")
async def list_catalog_songs(
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("editor")),
):
    """List catalog songs (id + title) for the produce-page song picker."""
    songs = await db.get_all_songs()
    return {
        "songs": [
            {"id": song["id"], "title": song.get("title", "Unknown")}
            for song in songs
        ]
    }


@router.post("/api/produce/analyze")
async def analyze_song(
    request: ProduceRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    _role: str = Depends(require_role("editor")),
):
    """Analyze a catalog song and return detected issues + recommended steps."""
    source_path = await run_in_threadpool(_resolve_source_path, request.song_id)
    result = await agent.execute_tool(
        "analyze_and_recommend_processing", {"file_path": str(source_path)}
    )
    return {"result": result}


@router.post("/api/produce/auto-clean")
async def auto_clean_song(
    request: ProduceRequest,
    agent: BigFlavorAgent = Depends(get_agent),
    _role: str = Depends(require_role("editor")),
):
    """Auto-clean a catalog song to a new derived file (original untouched)."""
    source_path = await run_in_threadpool(_resolve_source_path, request.song_id)
    output_path = _build_output_path(request.song_id)

    parameters: Dict[str, Any] = {
        "file_path": str(source_path),
        "output_path": str(output_path),
        "aggressiveness": request.aggressiveness,
    }
    if request.steps_override is not None:
        parameters["steps_override"] = request.steps_override

    result = await agent.execute_tool("auto_clean_recording", parameters)
    return {"result": result}
