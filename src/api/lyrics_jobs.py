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

**Vocal isolation.** Whisper transcribes sung vocals markedly better — both words
and timestamps — on an isolated vocal track than on a full mix, so extraction now
prefers isolated vocals: an already-separated ``vocals`` stem (issue #67) if the
song has one, otherwise a Demucs run inside the same job. Falling back to the raw
mix only happens when Demucs is unavailable or fails.

**Timings.** Whisper already returns a start/end per transcribed segment (and per
word when asked); those used to be discarded. They are now persisted to
``song_lyric_timings`` so the player can follow along with the song. The lyric
*text* still lives in ``text_embeddings`` exactly as before — timings are a
derived sidecar, never the search source of truth.
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi.concurrency import run_in_threadpool

from src.rag.big_flavor_rag import TEXT_EMBEDDING_DIM

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

# Transcription model used for extraction; recorded alongside the timings so a
# later re-run can tell which songs were done with which model.
WHISPER_MODEL = "large-v3"

# Shape version of the persisted `lines` document (see migration 11).
TIMINGS_FORMAT_VERSION = 1

AUDIO_SOURCE_MIX = "mix"
AUDIO_SOURCE_VOCALS = "vocals_stem"


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


def lyrics_signature(text: str) -> str:
    """Normalize lyric text to a comparable word sequence.

    Timings are only valid for the exact words they were measured against, so
    the save path compares signatures to decide whether an edit invalidated
    them. Case and whitespace/punctuation layout are irrelevant to that
    question — reflowing lines or fixing capitalization must NOT mark timings
    stale — so both are normalized away.
    """
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(cleaned.split())


def timings_text(lines: List[Dict[str, Any]]) -> str:
    """Reconstruct the transcript a timing document represents."""
    return " ".join((line.get("text") or "").strip() for line in lines)


def timings_view(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Shape a song_lyric_timings row for the API, or None when there is none.

    Drops the DB-internal columns (id, song_id, timestamps) and normalizes
    ``lines`` to a decoded list — some DatabaseManager methods return the raw
    JSONB string rather than a decoded document.
    """
    if not record:
        return None

    lines = record.get("lines")
    if isinstance(lines, str):
        lines = json.loads(lines)

    return {
        "format_version": record.get("format_version", TIMINGS_FORMAT_VERSION),
        "source": record.get("source"),
        "model": record.get("model"),
        "audio_source": record.get("audio_source"),
        "status": record.get("status"),
        "lines": lines or [],
    }


def _blocking_extract(
    audio_path: str,
    min_confidence: float = 0.5,
    vocals_path: Optional[str] = None,
    separate_vocals: bool = True,
    word_timestamps: bool = True,
) -> Dict[str, Any]:
    """Transcribe lyrics from an audio file (blocking; run in a threadpool).

    Prefers isolated vocals: ``vocals_path`` (an already-separated stem) is used
    directly when given, otherwise Demucs separates the mix in-process unless
    ``separate_vocals`` is off. Returns the lyric text, the per-segment timings,
    and which audio the transcription actually ran against.
    """
    from src.rag.lyrics_extractor import LyricsExtractor

    # An existing stem means no Demucs run is needed at all — don't pay to load it.
    reuse_stem = vocals_path is not None
    needs_demucs = separate_vocals and not reuse_stem

    extractor = LyricsExtractor(
        whisper_model_size=WHISPER_MODEL,
        use_gpu=True,
        min_confidence=min_confidence,
        load_demucs=needs_demucs,
    )
    if not extractor.is_available():
        raise RuntimeError("Lyrics extractor dependencies not installed")

    source = vocals_path or audio_path
    result = extractor.extract_lyrics(
        source,
        separate_vocals=needs_demucs,
        word_timestamps=word_timestamps,
    )
    if result.get("error"):
        raise RuntimeError(result["error"])

    # extract_lyrics reports whether separation actually happened; a reused stem
    # is already isolated vocals, so it counts either way.
    isolated = reuse_stem or bool(result.get("vocals_separated"))
    return {
        "lyrics": (result.get("lyrics") or "").strip(),
        "lines": result.get("segments") or [],
        "audio_source": AUDIO_SOURCE_VOCALS if isolated else AUDIO_SOURCE_MIX,
        "model": WHISPER_MODEL,
    }


class LyricsJobManager:
    """Tracks in-flight lyric-extraction tasks; status is in-memory only."""

    def __init__(self) -> None:
        self._tasks: Dict[int, asyncio.Task] = {}
        self._status: Dict[int, Dict[str, Optional[str]]] = {}

    def start(
        self,
        song_id: int,
        audio_path: str,
        rag,
        db=None,
        separate_vocals: bool = True,
    ) -> bool:
        """Kick off extraction for a song. Returns False if one is already running.

        ``db`` is optional so existing call sites keep working; without it the
        job can neither reuse an existing vocals stem nor persist timings, and
        degrades to the old text-only behaviour.
        """
        current = self._status.get(song_id)
        if current and current.get("status") == STATUS_RUNNING:
            return False
        self._status[song_id] = {"status": STATUS_RUNNING, "error": None}
        task = asyncio.create_task(
            self._run(song_id, audio_path, rag, db, separate_vocals)
        )
        self._tasks[song_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(song_id, None))
        return True

    async def _resolve_vocals_path(self, song_id: int, db) -> Optional[str]:
        """Path of a reusable, still-present vocals stem for the song, if any."""
        if db is None:
            return None
        try:
            path = await db.get_vocals_stem_path(song_id)
        except Exception:  # a stem lookup must never fail the extraction
            logger.warning("Vocals-stem lookup failed for song %s", song_id, exc_info=True)
            return None
        if path and os.path.exists(path):
            logger.info("Reusing separated vocals stem for song %s: %s", song_id, path)
            return path
        if path:
            logger.info(
                "Vocals stem recorded for song %s but missing on disk (%s); re-separating",
                song_id, path,
            )
        return None

    async def _run(
        self,
        song_id: int,
        audio_path: str,
        rag,
        db=None,
        separate_vocals: bool = True,
    ) -> None:
        """Run one extraction job, recording status. Never raises."""
        try:
            vocals_path = await self._resolve_vocals_path(song_id, db)
            result = await run_in_threadpool(
                _blocking_extract,
                audio_path,
                0.5,
                vocals_path,
                separate_vocals,
            )
            lyrics = result["lyrics"]
            if not lyrics:
                self._status[song_id] = {"status": STATUS_FAILED, "error": "No lyrics detected"}
                return

            await index_lyrics_text(rag, song_id, lyrics)

            if db is not None and result["lines"]:
                await db.save_lyric_timings(
                    song_id,
                    result["lines"],
                    source="whisper",
                    model=result["model"],
                    audio_source=result["audio_source"],
                    format_version=TIMINGS_FORMAT_VERSION,
                )

            self._status[song_id] = {"status": STATUS_COMPLETE, "error": None}
            logger.info(
                "Lyric extraction complete for song %s (%d lines, source=%s)",
                song_id, len(result["lines"]), result["audio_source"],
            )
        except Exception as exc:
            logger.exception("Lyric extraction failed for song %s", song_id)
            self._status[song_id] = {"status": STATUS_FAILED, "error": str(exc)}

    def status(self, song_id: int) -> Optional[Dict[str, Optional[str]]]:
        return self._status.get(song_id)


# Single process-wide manager instance the routes consult.
manager = LyricsJobManager()
