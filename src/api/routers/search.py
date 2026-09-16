"""Search + lyrics routes.

**No search route calls an LLM.** Every mode hits the RAG system directly, which
answers in tens of milliseconds; natural-language search used to route through
the agent for 2-12s and gained nothing by it, since the agent called this same
RAG function and only annotated the results afterwards. Those annotations now
live behind /api/search/explain, generated for one song when someone asks.

Lyrics lookups go through DatabaseManager methods (issue #8). Raw exceptions
propagate to the centralized error handlers (issue #9).
"""
import logging

from fastapi import APIRouter, HTTPException, Depends

from src.auth import require_role
from src.llm.llm_provider import get_llm_provider
from src.rag.big_flavor_rag import SongRAGSystem
from src.rag.explain import SYSTEM_PROMPT, build_explain_prompt, clean_explanation
from database import DatabaseManager
from src.api.dependencies import (
    DeepSearchRequest,
    ExplainMatchRequest,
    SearchRequest,
    TempoSearchRequest,
    AudioSimilaritySearchRequest,
    HybridSearchRequest,
    get_rag,
    get_db,
    get_agent,
)
from src.api.research_jobs import research_jobs, run_deep_search

logger = logging.getLogger("backend-api")

router = APIRouter()


@router.post("/api/search/natural")
async def natural_language_search(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Natural-language search: the same semantic+keyword ranking as /text.

    This used to call the agent, which called this very function and then spent
    seconds having an LLM write a sentence about each result. The ranking was
    identical either way, so the round-trip is gone; per-song explanations are
    available from /api/search/explain when a listener asks for one.
    """
    songs = await rag.search_by_text_description(
        description=request.query,
        limit=request.limit
    )

    return {
        "query": request.query,
        "search_summary": None,
        "songs": songs,
        "total_found": len(songs),
        "limit": request.limit
    }


@router.post("/api/search/deep/start")
async def start_deep_search(
    request: DeepSearchRequest,
    db: DatabaseManager = Depends(get_db),
    _role: str = Depends(require_role("listener")),
):
    """Begin an in-depth search and return its job id immediately.

    The loop makes several model calls and several retrievals, so it runs in the
    background and reports its steps; the client polls
    /api/search/deep/{job_id}.
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="A question is required")

    agent = await get_agent()

    return research_jobs.start(
        query,
        lambda emit: run_deep_search(query, agent, db, emit),
    )


@router.get("/api/search/deep/{job_id}")
async def deep_search_status(
    job_id: str,
    _role: str = Depends(require_role("listener")),
):
    """An in-depth search's steps so far, and its answer once it has one."""
    status = research_jobs.status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="That search is no longer available")
    return status


@router.post("/api/search/explain")
async def explain_match(
    request: ExplainMatchRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Explain why one song matched one query, grounded in that song's own data.

    The only LLM call anywhere near search, and it happens once, for one song,
    because someone clicked to ask.
    """
    song = await db.get_song(request.song_id)
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")

    lyrics = await db.get_song_lyrics(request.song_id)
    prompt = build_explain_prompt(request.query, dict(song), lyrics)

    provider = get_llm_provider()
    response = await provider.generate_response(
        messages=[{"role": "user", "content": prompt}],
        system=SYSTEM_PROMPT,
        max_tokens=120,
        temperature=0.2,
    )

    reason = clean_explanation(response)
    if not reason:
        raise HTTPException(status_code=502, detail="Could not generate an explanation")

    logger.info("Explained match for song %s", request.song_id)
    return {"song_id": request.song_id, "reason": reason}


@router.post("/api/search/text")
async def search_by_text(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by text description using semantic search"""
    results = await rag.search_by_text_description(
        description=request.query,
        limit=request.limit
    )
    return {"results": results}


@router.post("/api/search/lyrics")
async def search_by_lyrics(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by lyrics keywords"""
    results = await rag.search_lyrics_by_keyword(
        keyword=request.query,
        limit=request.limit
    )
    return {"results": results}


@router.post("/api/search/tempo")
async def search_by_tempo(
    request: TempoSearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Direct tempo (BPM) search — deterministic, no agent round-trip.

    Returns catalog songs whose tempo falls in the [min_bpm, max_bpm] band,
    ordered by tempo. An empty or invalid band (neither bound set, or
    min > max) yields an empty result rather than an error.
    """
    if request.min_bpm is None and request.max_bpm is None:
        return {"results": []}
    if (
        request.min_bpm is not None
        and request.max_bpm is not None
        and request.min_bpm > request.max_bpm
    ):
        return {"results": []}

    results = await rag.search_by_tempo_range(
        min_tempo=request.min_bpm,
        max_tempo=request.max_bpm,
        limit=request.limit
    )
    return {"results": results}


@router.post("/api/search/audio")
async def search_by_audio(
    request: AudioSimilaritySearchRequest,
    rag: SongRAGSystem = Depends(get_rag),
    db: DatabaseManager = Depends(get_db)
):
    """Direct audio-similarity search referencing an existing catalog song.

    Returns catalog songs acoustically similar to the reference song based on
    its stored audio embedding (deterministic). A valid song with no stored
    embedding yields an empty list.
    """
    if await db.get_song(request.song_id) is None:
        raise HTTPException(status_code=404, detail="Song not found")

    results = await rag.search_related_songs(request.song_id, limit=request.limit)
    return {"results": results}


@router.post("/api/search/hybrid")
async def search_hybrid(
    request: HybridSearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Direct hybrid search — text/mood description combined with a tempo band.

    Runs on the RAG read path (deterministic). An empty query, or an invalid
    tempo band (min > max), yields an empty result rather than an error.
    """
    if not request.query or not request.query.strip():
        return {"results": []}

    results = await rag.search_text_with_tempo(
        description=request.query.strip(),
        min_tempo=request.min_bpm,
        max_tempo=request.max_bpm,
        limit=request.limit
    )
    return {"results": results}


@router.get("/api/songs/{song_id}/related")
async def get_related_songs(
    song_id: int,
    limit: int = 10,
    rag: SongRAGSystem = Depends(get_rag),
    db: DatabaseManager = Depends(get_db)
):
    """Find catalog songs that sound like the given song (audio more-like-this).

    Returns a ranked list (most similar first) of other catalog songs based on
    the source song's stored audio embedding. A valid song with no stored
    embedding yields an empty list rather than an error.
    """
    if await db.get_song(song_id) is None:
        raise HTTPException(status_code=404, detail="Song not found")

    results = await rag.search_related_songs(song_id, limit=limit)
    return {"results": results}


@router.get("/api/songs/{song_id}/lyrics")
async def get_song_lyrics(
    song_id: int,
    db: DatabaseManager = Depends(get_db)
):
    """Get lyrics for a specific song"""
    if await db.get_song(song_id) is None:
        raise HTTPException(status_code=404, detail="Song not found")

    lyrics = await db.get_song_lyrics(song_id)

    if lyrics is not None:
        return {"lyrics": lyrics}
    else:
        return {"lyrics": "Lyrics not available for this song."}


@router.get("/api/songs/{song_id}/lyrics/timed")
async def get_song_timed_lyrics(
    song_id: int,
    db: DatabaseManager = Depends(get_db)
):
    """Get a song's lyrics with per-line timings, for follow-along playback.

    Listener-scoped on purpose: the editor-facing lyric routes live under
    /api/produce/* behind an editor role, but every listener's player needs to
    read these. Read-only, and never returns the "not available" placeholder the
    plain lyrics route uses — a player wants an empty string, not prose.

    ``timings`` is null when the song has never been extracted with timings; the
    client falls back to showing static lyrics. A ``stale`` status means the text
    was hand-edited after extraction, so the timings no longer line up.
    """
    from src.api import lyrics_jobs

    if await db.get_song(song_id) is None:
        raise HTTPException(status_code=404, detail="Song not found")

    lyrics = await db.get_song_lyrics(song_id)
    timings = await db.get_lyric_timings(song_id)

    return {
        "song_id": song_id,
        "lyrics": lyrics or "",
        "timings": lyrics_jobs.timings_view(timings),
    }
