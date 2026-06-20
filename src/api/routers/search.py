"""Search routes — call the RAG system directly (fast path, no LLM round-trip)."""
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
    try:
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
    except Exception as e:
        import traceback
        print(f"ERROR in natural_language_search: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/search/text")
async def search_by_text(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by text description using semantic search"""
    try:
        results = await rag.search_by_text_description(
            description=request.query,
            limit=request.limit
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/search/lyrics")
async def search_by_lyrics(
    request: SearchRequest,
    rag: SongRAGSystem = Depends(get_rag)
):
    """Search songs by lyrics keywords"""
    try:
        results = await rag.search_lyrics_by_keyword(
            keyword=request.query,
            limit=request.limit
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/songs/{song_id}/lyrics")
async def get_song_lyrics(
    song_id: int,
    db: DatabaseManager = Depends(get_db)
):
    """Get lyrics for a specific song"""
    try:
        query = """
            SELECT content as lyrics
            FROM text_embeddings
            WHERE song_id = $1 AND content_type = 'lyrics'
        """
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)

        if row:
            return {"lyrics": row["lyrics"]}
        else:
            return {"lyrics": "Lyrics not available for this song."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
