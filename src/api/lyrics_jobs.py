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
prefers isolated vocals: already-separated vocal stems (issue #67) if the song
has them, otherwise a Demucs run inside the same job. Falling back to the raw
mix only happens when Demucs is unavailable or fails.

**Which vocal stems.** A session song has one stem per mic, so it can have
several vocal tracks (``vocals``, ``vocals-2``, ...) — and ``vocals`` is just
whichever mic came first in the Reaper session, often not the lead singer. By
default every stem with "vocal" in its name is mixed and transcribed together;
the editor can pick a different set (``stem_ids``). The stems come from the
stem set made from the very version being transcribed, so the timings line up
with the audio the player plays rather than with some other take.

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
import tempfile
from typing import Any, Dict, List, Optional, Sequence

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
    await rag.index_text_content(song_id, "lyrics", text, embedding)


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


def _mix_vocal_stems(paths: Sequence[str], output_path: str) -> str:
    """Sum several vocal stems into one file Whisper can read.

    Two singers on two mics are one performance: transcribing each mic alone
    would duplicate every line that bleeds into the other, so they're mixed —
    the same reason ``session_transcribe.build_vocal_mix`` does it for takes.
    """
    import soundfile as sf

    from src.production.session_render import mix_audio_files

    # Stems of one set share a sample rate; the mixer sums samples as-is.
    sample_rate = sf.info(paths[0]).samplerate
    mix_audio_files(paths, output_path, sample_rate)
    return output_path


def _blocking_extract(
    audio_path: str,
    min_confidence: float = 0.5,
    vocals_paths: Sequence[str] = (),
    separate_vocals: bool = True,
    word_timestamps: bool = True,
    extractor=None,
) -> Dict[str, Any]:
    """Transcribe lyrics from an audio file (blocking; run in a threadpool).

    Prefers isolated vocals: ``vocals_paths`` (already-separated stems, mixed
    together when there are several) are used directly when given, otherwise
    Demucs separates the mix in-process unless ``separate_vocals`` is off.
    Returns the lyric text, the per-segment timings, and which audio the
    transcription actually ran against.

    ``extractor`` lets a caller supply an already-constructed ``LyricsExtractor``
    instead of building one per call. A single request doesn't care, but loading
    Whisper large-v3 takes tens of seconds, so a catalog-wide backfill that built
    one per song would spend hours doing nothing but loading models — the batch
    script passes one in and reuses it across every track.
    """
    from src.rag.lyrics_extractor import LyricsExtractor

    # An existing stem means no Demucs run is needed at all — don't pay to load it.
    reuse_stem = bool(vocals_paths)
    needs_demucs = separate_vocals and not reuse_stem

    if extractor is None:
        extractor = LyricsExtractor(
            whisper_model_size=WHISPER_MODEL,
            use_gpu=True,
            min_confidence=min_confidence,
            load_demucs=needs_demucs,
        )
    if not extractor.is_available():
        raise RuntimeError("Lyrics extractor dependencies not installed")

    with tempfile.TemporaryDirectory() as temp_dir:
        if len(vocals_paths) > 1:
            source = _mix_vocal_stems(
                vocals_paths, os.path.join(temp_dir, "vocals-mix.wav")
            )
        else:
            source = vocals_paths[0] if vocals_paths else audio_path
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


def is_vocal_stem(stem: Dict[str, Any]) -> bool:
    """Whether a stem is picked for transcription by default.

    Matches "vocal" in the bucket name (``vocals``, ``vocals-2`` — a session
    track named "Kev Vox" lands in that bucket) or in the producer's own label.
    """
    names = (stem.get("name") or "", stem.get("display_name") or "")
    return any("vocal" in name.lower() for name in names)


async def find_lyrics_stem_set(
    song_id: int, db, source_version_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """The stem set to offer vocal tracks from, with its stems, or None.

    The newest complete set made from ``source_version_id`` — the audio being
    transcribed — so a session song's lyrics come from the same take the player
    plays. A catalog song (``source_version_id`` None) falls back to its newest
    set when none was made from the original: a cleaned version keeps the
    original's timeline, so its stems still line up.
    """
    stem_sets = [
        s for s in await db.list_stem_sets(song_id) if s.get("status") == "complete"
    ]
    matching = [s for s in stem_sets if s.get("source_version_id") == source_version_id]
    if not matching and source_version_id is None:
        matching = stem_sets
    if not matching:
        return None
    stem_set = matching[0]
    return {"stem_set": stem_set, "stems": await db.list_stems(stem_set["id"])}


async def resolve_vocals_paths(
    song_id: int,
    db,
    source_version_id: Optional[int] = None,
    stem_ids: Optional[Sequence[int]] = None,
) -> List[str]:
    """Paths of the still-present vocal stems to transcribe, possibly none.

    ``stem_ids`` is the editor's choice; None means the default (every
    vocal-named stem) and an empty list means "use the full mix". A recorded
    stem whose file has since been cleaned up is skipped, and with none left the
    caller separates again rather than failing on a missing path.
    """
    if db is None:
        return []
    try:
        found = await find_lyrics_stem_set(song_id, db, source_version_id)
    except Exception:  # a stem lookup must never fail the extraction
        logger.warning("Vocals-stem lookup failed for song %s", song_id, exc_info=True)
        return []
    if found is None:
        return []

    if stem_ids is None:
        chosen = [s for s in found["stems"] if is_vocal_stem(s)]
    else:
        wanted = set(stem_ids)
        chosen = [s for s in found["stems"] if s["id"] in wanted]

    paths = []
    for stem in chosen:
        if os.path.exists(stem["path"]):
            paths.append(stem["path"])
        else:
            logger.info(
                "Vocals stem %s recorded for song %s but missing on disk (%s)",
                stem["name"], song_id, stem["path"],
            )
    if paths:
        logger.info("Reusing separated vocals stems for song %s: %s", song_id, paths)
    return paths


async def extract_and_store(
    song_id: int,
    audio_path: str,
    rag,
    db=None,
    separate_vocals: bool = True,
    extractor=None,
    source_version_id: Optional[int] = None,
    stem_ids: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """Transcribe one song and persist its lyrics + timings. Returns a summary.

    The single seam both the background job (``LyricsJobManager``) and the
    catalog backfill script go through, so the two can't drift on which audio is
    transcribed or how the result is stored.

    Raises ``RuntimeError`` when nothing was transcribed — an empty transcript is
    a failure to report, not a result to store. ``db`` is optional; without it
    the lyric text is still indexed but timings have nowhere to go.
    """
    vocals_paths = await resolve_vocals_paths(song_id, db, source_version_id, stem_ids)
    result = await run_in_threadpool(
        _blocking_extract,
        audio_path,
        0.5,
        vocals_paths,
        separate_vocals,
        True,
        extractor,
    )

    lyrics = result["lyrics"]
    if not lyrics:
        raise RuntimeError("No lyrics detected")

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

    return {
        "song_id": song_id,
        "lyrics": lyrics,
        "line_count": len(result["lines"]),
        "audio_source": result["audio_source"],
        "model": result["model"],
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
        source_version_id: Optional[int] = None,
        stem_ids: Optional[Sequence[int]] = None,
    ) -> bool:
        """Kick off extraction for a song. Returns False if one is already running.

        ``db`` is optional so existing call sites keep working; without it the
        job can neither reuse an existing vocals stem nor persist timings, and
        degrades to the old text-only behaviour. ``source_version_id`` and
        ``stem_ids`` pass through to ``extract_and_store``.
        """
        current = self._status.get(song_id)
        if current and current.get("status") == STATUS_RUNNING:
            return False
        self._status[song_id] = {"status": STATUS_RUNNING, "error": None}
        task = asyncio.create_task(
            self._run(
                song_id, audio_path, rag, db, separate_vocals,
                source_version_id, stem_ids,
            )
        )
        self._tasks[song_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(song_id, None))
        return True

    async def _run(
        self,
        song_id: int,
        audio_path: str,
        rag,
        db=None,
        separate_vocals: bool = True,
        source_version_id: Optional[int] = None,
        stem_ids: Optional[Sequence[int]] = None,
    ) -> None:
        """Run one extraction job, recording status. Never raises."""
        try:
            summary = await extract_and_store(
                song_id, audio_path, rag, db, separate_vocals,
                source_version_id=source_version_id, stem_ids=stem_ids,
            )
            self._status[song_id] = {"status": STATUS_COMPLETE, "error": None}
            logger.info(
                "Lyric extraction complete for song %s (%d lines, source=%s)",
                song_id, summary["line_count"], summary["audio_source"],
            )
        except Exception as exc:
            logger.exception("Lyric extraction failed for song %s", song_id)
            self._status[song_id] = {"status": STATUS_FAILED, "error": str(exc)}

    def status(self, song_id: int) -> Optional[Dict[str, Optional[str]]]:
        return self._status.get(song_id)


# Single process-wide manager instance the routes consult.
manager = LyricsJobManager()
