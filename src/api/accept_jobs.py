"""Background runner for "accept all fixes" renders.

Rendering a review queue means chain-applying every accepted fix to every stem,
remixing, then running the master chain — minutes of CPU for a song with a dozen
or more fixes. It used to run inside the request, so a big queue outlived the
edge proxy's 60s read timeout and came back as an HTML error page; the UI could
only suggest turning fixes off until the render fit. Turning fixes off to make a
save succeed is not a real option, so the render now runs as a background task
the producer polls, like stem separation (``stem_jobs.py``) and lyric extraction
(``lyrics_jobs.py``).

Status is tracked **in memory, keyed by song**: one render per song at a time,
which is also what the UI offers. The *result* is durable — a completed save is
a row in ``song_versions`` — so a restart mid-render only loses the progress
indicator, and the producer re-triggers. A preview's result is a rendered file
under the produced directory, which likewise outlives this manager.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("backend-api")

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

# A finished job stays readable for a whole working session: the versions list
# keeps a row for a rendered-but-unsaved mix so it can be auditioned against the
# original, and that row vanishing out from under a producer mid-session would
# be worse than holding a little state. Cleared on dismiss or the next render.
RESULT_TTL_SECONDS = 8 * 60 * 60


def fingerprint(payload: Dict[str, Any]) -> str:
    """Identify a render by the audio it would produce.

    Covers the source version and every stem/master fix with its parameters —
    everything that changes the output samples — and deliberately excludes
    ``preview``, because previewing and saving render byte-identical audio. That
    is what lets the render kicked off by Start analysis satisfy a later Save.
    """
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class AcceptJobManager:
    """Tracks one in-flight accept-fixes render per song."""

    def __init__(self) -> None:
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._tasks: Dict[int, asyncio.Task] = {}
        # song_id -> (fingerprint, rendered file). The rendered mix from the
        # last successful render, kept so an unchanged fix set never renders
        # twice: Start analysis warms this, and Preview/Save then hit it.
        self._renders: Dict[int, Dict[str, Any]] = {}

    def cached_render(self, song_id: int, print_: str) -> Optional[str]:
        """The already-rendered file for this exact fix set, if it still exists."""
        entry = self._renders.get(song_id)
        if not entry or entry["fingerprint"] != print_:
            return None
        if not os.path.exists(entry["path"]):
            # Rendered files live on disk under the produced directory; if one
            # was cleaned up, fall through to a fresh render.
            self._renders.pop(song_id, None)
            return None
        return entry["path"]

    def remember_render(
        self,
        song_id: int,
        print_: str,
        path: str,
        notices: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._renders[song_id] = {
            "fingerprint": print_, "path": path, "notices": notices or [],
        }

    def cached_notices(self, song_id: int, print_: str) -> List[Dict[str, Any]]:
        """What the remembered render reported doing less of than asked.

        Stored with the render rather than the job: a reused render answers a
        later request that never ran the DSP itself, and a producer accepting
        that result needs the same warning the first one got (issue #91).
        """
        entry = self._renders.get(song_id)
        if not entry or entry["fingerprint"] != print_:
            return []
        return entry.get("notices") or []

    def is_running(self, song_id: int) -> bool:
        job = self._jobs.get(song_id)
        return bool(job and job["status"] == STATUS_RUNNING)

    def start(
        self,
        song_id: int,
        preview: bool,
        fix_count: int,
        render: Callable[[], Awaitable[Dict[str, Any]]],
        fingerprint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Begin a render. Raises RuntimeError if one is already going."""
        if self.is_running(song_id):
            raise RuntimeError("A render is already running for this song")

        job = {
            "job_id": uuid.uuid4().hex,
            "song_id": song_id,
            "status": STATUS_RUNNING,
            "preview": preview,
            "fix_count": fix_count,
            "fingerprint": fingerprint,
            "started_at": time.time(),
            "finished_at": None,
            "version": None,
            "candidate_path": None,
            "notices": [],
            "error": None,
        }
        self._jobs[song_id] = job

        task = asyncio.create_task(self._run(song_id, render))
        self._tasks[song_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(song_id, None))

        logger.info(
            "Accept-fixes render started for song %s (job %s, %d fixes, preview=%s)",
            song_id, job["job_id"], fix_count, preview,
        )
        return self.status(song_id)

    async def _run(
        self,
        song_id: int,
        render: Callable[[], Awaitable[Dict[str, Any]]],
    ) -> None:
        """Run one render, recording the outcome on the job. Never raises."""
        job = self._jobs[song_id]
        try:
            result = await render()
            job["version"] = result.get("version")
            job["candidate_path"] = result.get("candidate_path")
            job["notices"] = result.get("notices") or []
            job["status"] = STATUS_COMPLETE
            logger.info(
                "Accept-fixes render complete for song %s (job %s)", song_id, job["job_id"]
            )
        except Exception as exc:  # a failed render must be visible to the poller
            logger.exception("Accept-fixes render failed for song %s", song_id)
            job["status"] = STATUS_FAILED
            # HTTPException carries the useful message on .detail; its str() is
            # the status code, which tells the producer nothing.
            job["error"] = str(getattr(exc, "detail", None) or exc)
        finally:
            job["finished_at"] = time.time()

    def complete_now(
        self,
        song_id: int,
        preview: bool,
        fix_count: int,
        result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Record an already-finished render — a cache hit, with nothing to wait for."""
        now = time.time()
        self._jobs[song_id] = {
            "job_id": uuid.uuid4().hex,
            "song_id": song_id,
            "status": STATUS_COMPLETE,
            "preview": preview,
            "fix_count": fix_count,
            "fingerprint": None,
            "reused": True,
            "started_at": now,
            "finished_at": now,
            "version": result.get("version"),
            "candidate_path": result.get("candidate_path"),
            "notices": result.get("notices") or [],
            "error": None,
        }
        return self.status(song_id)

    def status(self, song_id: int) -> Dict[str, Any]:
        """The current (or most recent, within the TTL) render for a song."""
        job = self._jobs.get(song_id)
        if job is None:
            return {"status": STATUS_IDLE, "song_id": song_id}

        finished_at = job.get("finished_at")
        if finished_at is not None and time.time() - finished_at > RESULT_TTL_SECONDS:
            self._jobs.pop(song_id, None)
            return {"status": STATUS_IDLE, "song_id": song_id}

        return dict(job)

    def clear(self, song_id: int) -> None:
        """Forget a finished job, so the UI can dismiss a result or an error."""
        job = self._jobs.get(song_id)
        if job and job["status"] != STATUS_RUNNING:
            self._jobs.pop(song_id, None)


# One manager for the process, mirroring the other job runners.
accept_jobs = AcceptJobManager()
