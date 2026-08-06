"""Background stem-separation job runner (issue #67).

Stem separation takes minutes, so — like the catalog-clean batch
(``produce_batch.py``) — it runs as a background task that the producer polls
rather than a synchronous request. Unlike the batch runner, each job's lifecycle
is persisted on the ``song_stem_sets.status`` column (queued -> running ->
complete | failed), so status survives a poll gap and a producer can always tell
a failed separation from a successful one by listing the song's stem sets.

This manager owns the in-process asyncio tasks; the durable state lives in the
DB. Separation itself is CPU-bound (Demucs), so it runs in a threadpool and never
blocks the event loop.
"""
import asyncio
import logging
from pathlib import Path
from typing import Dict, List

from fastapi.concurrency import run_in_threadpool

from src.production import (
    audio_preview,
    instrument_tagging,
    stem_separation,
    waveform_peaks,
)
from database import DatabaseManager

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


class StemJobManager:
    """Tracks running stem-separation tasks; durable status lives in the DB."""

    def __init__(self) -> None:
        # stem_set_id -> Task, so a job isn't garbage-collected while it runs.
        self._tasks: Dict[int, asyncio.Task] = {}

    def start(
        self,
        stem_set_id: int,
        source_path: str,
        output_dir: str,
        model_name: str,
        db: DatabaseManager,
    ) -> None:
        """Kick off separation for an already-created (queued) stem set."""
        task = asyncio.create_task(
            self._run(stem_set_id, source_path, output_dir, model_name, db)
        )
        self._tasks[stem_set_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(stem_set_id, None))

    async def _run(
        self,
        stem_set_id: int,
        source_path: str,
        output_dir: str,
        model_name: str,
        db: DatabaseManager,
    ) -> None:
        """Run one separation job, recording status/stems in the DB. Never raises."""
        await db.set_stem_set_status(stem_set_id, STATUS_RUNNING)
        try:
            stems = await run_in_threadpool(
                stem_separation.separate_stems, source_path, output_dir, model_name
            )
            rows = [
                await db.add_stem(stem_set_id, stem["name"], stem["path"])
                for stem in stems
            ]
            await db.set_stem_set_status(stem_set_id, STATUS_COMPLETE)
            logger.info("Stem set %s complete (%d stems)", stem_set_id, len(stems))
            # The passes below all run over stems that already exist, after the
            # set is marked complete, in the order the console needs them:
            # peaks to draw anything at all, previews to press play, and the
            # instrument labels — purely cosmetic — last.
            await warm_stem_peaks(rows, db)
            await warm_stem_previews(rows)
            await tag_stems(rows, db)
        except Exception as exc:  # separation failure must be visible via status
            logger.exception("Stem separation failed for stem set %s", stem_set_id)
            # Best-effort cleanup of any partial output so a failed run leaves no
            # half-written stems masquerading as usable.
            try:
                await run_in_threadpool(_remove_dir, output_dir)
            except Exception:
                logger.warning("Could not clean up partial stem output %s", output_dir)
            await db.set_stem_set_status(stem_set_id, STATUS_FAILED, str(exc))


async def warm_stem_peaks(stems: List[Dict], db: DatabaseManager) -> None:
    """Precompute each stem's waveform drawing envelope. Best-effort.

    The console fetches these on open and computes any that are missing, so this
    only decides whether the *first* open of a fresh set pays for it. A failure
    must never fail a separation that produced usable stems — it just leaves
    ``waveform_peaks`` NULL for the endpoint to fill in on demand.
    """
    for stem in stems:
        try:
            peaks = await run_in_threadpool(
                waveform_peaks.compute_peaks, stem["path"]
            )
            await db.set_stem_waveform_peaks(stem["id"], peaks)
        except Exception:
            logger.exception(
                "Waveform peaks failed for stem %s (%s)", stem["id"], stem["name"]
            )


async def warm_stem_previews(stems: List[Dict]) -> None:
    """Pre-transcode each stem's compressed playback copy. Best-effort.

    No DB write — the file on disk is the whole cache. Like peaks, the endpoint
    builds any that are missing, so a failure here only means the first producer
    to press play waits for the encode.
    """
    for stem in stems:
        try:
            source = Path(stem["path"])
            await run_in_threadpool(
                audio_preview.build_preview,
                str(source),
                str(audio_preview.stem_preview_path(source)),
            )
        except Exception:
            logger.exception(
                "Preview transcode failed for stem %s (%s)", stem["id"], stem["name"]
            )


async def tag_stems(stems: List[Dict], db: DatabaseManager) -> None:
    """Identify and record the instruments in each stem. Best-effort.

    A tagging failure must never fail (or roll back) a separation that already
    produced usable stems — the labels are an aid to naming what a stem holds,
    not part of the audio. Failures are logged and leave ``instrument_tags``
    NULL, which the API reports as "not identified" and a producer can retry
    per stem.
    """
    for stem in stems:
        try:
            tags = await run_in_threadpool(
                instrument_tagging.identify_instruments, stem["path"]
            )
            await db.set_stem_instrument_tags(stem["id"], tags)
        except Exception:
            logger.exception(
                "Instrument tagging failed for stem %s (%s)", stem["id"], stem["name"]
            )


def _remove_dir(path: str) -> None:
    """Recursively remove a directory tree if present. Synchronous (filesystem)."""
    import shutil

    target = Path(path)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


# Single process-wide manager instance the routes consult.
manager = StemJobManager()
