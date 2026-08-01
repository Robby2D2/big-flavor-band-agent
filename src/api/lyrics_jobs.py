"""Background lyric-extraction job runner + lyric indexing helpers.

Lyric extraction runs Whisper (large-v3, optionally Demucs) and takes minutes, so
— like stem separation (``stem_jobs.py``) — it runs as a background task the
producer polls rather than a synchronous request. Unlike stems, the *result* is
already durably persisted (the lyrics land in ``text_embeddings``), so this
manager only needs to track the transient run status in memory; a server restart
mid-extract just leaves the status ``idle`` and the producer can re-trigger.

The heavy transcription runs in a threadpool so it never blocks the event loop;
the DB write (which uses the asyncpg pool bound to the main loop) runs on the
loop. ``index_lyrics_text`` is shared with the manual-save (PUT) path so edited
and extracted lyrics are stored + embedded identically.
"""
import asyncio
import logging
from typing import Dict, Optional

from fastapi.concurrency import run_in_threadpool

from src.rag.big_flavor_rag import TEXT_EMBEDDING_DIM

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


def _embed_text(rag, text: str):
    """Compute the text embedding for lyrics, or a zero placeholder.

    Falls back to a zero vector of the schema dimension when the text model is
    unavailable (sentence-transformers not installed) or encoding fails, so the
    content is always stored even if lyric *search* can't rank it.
    """
    model = getattr(rag, "text_embedding_model", None)
    if model is not None and text.strip():
        try:
            return model.encode(text).tolist()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Text embedding failed, storing zero vector: %s", exc)
    return [0.0] * TEXT_EMBEDDING_DIM


async def index_lyrics_text(rag, song_id: int, text: str) -> None:
    """Embed + upsert lyrics into text_embeddings (content_type 'lyrics').

    Shared by the manual-save (PUT) endpoint and the extraction job so both
    persist identically and keep lyric search consistent.
    """
    embedding = await run_in_threadpool(_embed_text, rag, text)
    await rag.store_text_embedding(song_id, "lyrics", text, embedding)


def _blocking_extract(audio_path: str, min_confidence: float = 0.5) -> str:
    """Transcribe lyrics from an audio file (blocking; run in a threadpool)."""
    from src.rag.lyrics_extractor import LyricsExtractor

    extractor = LyricsExtractor(
        whisper_model_size="large-v3",
        use_gpu=True,
        min_confidence=min_confidence,
        load_demucs=False,  # skip vocal separation for speed; Whisper handles the mix
    )
    if not extractor.is_available():
        raise RuntimeError("Lyrics extractor dependencies not installed")

    result = extractor.extract_lyrics(audio_path, separate_vocals=False)
    if result.get("error"):
        raise RuntimeError(result["error"])
    return (result.get("lyrics") or "").strip()


class LyricsJobManager:
    """Tracks in-flight lyric-extraction tasks; status is in-memory only."""

    def __init__(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}
        self._status: Dict[int, Dict[str, Optional[str]]] = {}

    def start(self, song_id: int, audio_path: str, rag) -> bool:
        """Kick off extraction for a song. Returns False if one is already running."""
        current = self._status.get(song_id)
        if current and current.get("status") == STATUS_RUNNING:
            return False
        self._status[song_id] = {"status": STATUS_RUNNING, "error": None}
        task = asyncio.create_task(self._run(song_id, audio_path, rag))
        self._tasks[song_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(song_id, None))
        return True

    async def _run(self, song_id: int, audio_path: str, rag) -> None:
        """Run one extraction job, recording status. Never raises."""
        try:
            lyrics = await run_in_threadpool(_blocking_extract, audio_path)
            if not lyrics:
                self._status[song_id] = {"status": STATUS_FAILED, "error": "No lyrics detected"}
                return
            await index_lyrics_text(rag, song_id, lyrics)
            self._status[song_id] = {"status": STATUS_COMPLETE, "error": None}
            logger.info("Lyric extraction complete for song %s", song_id)
        except Exception as exc:
            logger.exception("Lyric extraction failed for song %s", song_id)
            self._status[song_id] = {"status": STATUS_FAILED, "error": str(exc)}

    def status(self, song_id: int) -> Optional[Dict[str, Optional[str]]]:
        return self._status.get(song_id)


# Single process-wide manager instance the routes consult.
manager = LyricsJobManager()
