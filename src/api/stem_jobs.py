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
from typing import Dict

from fastapi.concurrency import run_in_threadpool

from src.production import stem_separation
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
            for stem in stems:
                await db.add_stem(stem_set_id, stem["name"], stem["path"])
            await db.set_stem_set_status(stem_set_id, STATUS_COMPLETE)
            logger.info("Stem set %s complete (%d stems)", stem_set_id, len(stems))
        except Exception as exc:  # separation failure must be visible via status
            logger.exception("Stem separation failed for stem set %s", stem_set_id)
            # Best-effort cleanup of any partial output so a failed run leaves no
            # half-written stems masquerading as usable.
            try:
                await run_in_threadpool(_remove_dir, output_dir)
            except Exception:
                logger.warning("Could not clean up partial stem output %s", output_dir)
            await db.set_stem_set_status(stem_set_id, STATUS_FAILED, str(exc))


def _remove_dir(path: str) -> None:
    """Recursively remove a directory tree if present. Synchronous (filesystem)."""
    import shutil

    target = Path(path)
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)


# Single process-wide manager instance the routes consult.
manager = StemJobManager()
