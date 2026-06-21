"""Search + lyrics routes.

Natural-language search goes through the agent; text/lyrics search hit the RAG
system directly (fast path, no LLM round-trip). Lyrics lookups go through
DatabaseManager methods (issue #8). Raw exceptions propagate to the centralized
error handlers (issue #9).
"""
from fastapi import APIRouter, HTTPException, Depends

from src.rag.big_flavor_rag import SongRAGSystem
from database import DatabaseManager
from src.api.dependencies import SearchRequest, get_rag, get_db, get_agent

router = APIRouter()


@router.post("/api/search/natural")
async def natural_language_search(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """
    Natural language search using the agent to interpret the query
    and use the appropriate tools
    """
    agent_instance = await get_agent()

    # Use the agent's search_songs method to get both text and song data
    result = await agent_instance.search_songs(request.query, request.limit)

    return {
        "query": request.query,
        "search_summary": result.get("search_summary"),
        "songs": result["songs"],
        "total_found": result["total_found"],
        "limit": request.limit
    }


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
