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

Nothing is rendered twice. Fixes used to render once on Start analysis and again
on play or save; two caches see to that now:

* :class:`ChainCache` — one entry per *chain*: a source file run through a list
  of fixes. Every path that applies fixes (the whole-queue render, a stem's
  play-time preview, the full mix's) reads and fills it, so pressing play after
  analysis plays files that already exist, and changing one stem's fixes
  re-renders that stem alone.
* the per-song whole-queue cache in :class:`AcceptJobManager` — the finished mix
  for a fix set, so Save after Start analysis is an insert. It holds several
  fix sets per song: it used to hold one, and a master-only preview for the
  full-mix row silently evicted the 21-fix render a Save was about to reuse.

A render reports its progress step by step and can be cancelled between steps
(PROD-19) — never once the version is being written.
"""
import asyncio
import hashlib
import json
import logging
import os
import time
import uuid
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("backend-api")

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

#: The render is writing the version row; cancelling now could leave a
#: half-saved version, so it is refused (PROD-19).
STAGE_SAVING = "saving"

#: Whole-queue renders remembered per song. A handful covers flipping a fix on
#: and off and back; each entry is a path and a little metadata.
RENDERS_PER_SONG = 8

#: Chains remembered across the process. A queue is ~20 chains, so this holds
#: many songs' worth; the files themselves live on disk under produced/.
CHAIN_CACHE_SIZE = 512

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


class ChainCache:
    """(source file, fix chain) -> the rendered file and what its tools reported.

    Keyed by the source *path*: a stem, a version or a downmix file is never
    rewritten in place (re-separating makes a new set directory), so the path
    names the audio. An entry whose file has gone is a miss.
    """

    def __init__(self, size: int = CHAIN_CACHE_SIZE) -> None:
        self._size = size
        self._entries: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    @staticmethod
    def key(source_path: str, chain: List[Dict[str, Any]]) -> str:
        return fingerprint({"source": str(source_path), "chain": chain})

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if not os.path.exists(entry["path"]):
            self._entries.pop(key, None)
            return None
        self._entries.move_to_end(key)
        return entry

    def put(
        self, key: str, path: str, notices: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        self._entries[key] = {"path": path, "notices": notices or []}
        self._entries.move_to_end(key)
        while len(self._entries) > self._size:
            self._entries.popitem(last=False)


class RenderCancelled(Exception):
    """Raised by a render step once its job has been cancelled."""


class AcceptJobManager:
    """Tracks one in-flight accept-fixes render per song."""

    def __init__(self) -> None:
        self._jobs: Dict[int, Dict[str, Any]] = {}
        self._tasks: Dict[int, asyncio.Task] = {}
        # song_id -> fingerprint -> rendered mix, newest last. Kept so an
        # unchanged fix set never renders twice: Start analysis warms this, and
        # Preview/Save then hit it — even after other fix sets were rendered.
        self._renders: Dict[int, "OrderedDict[str, Dict[str, Any]]"] = {}

    def _entry(self, song_id: int, print_: str) -> Optional[Dict[str, Any]]:
        return self._renders.get(song_id, {}).get(print_)

    def cached_render(self, song_id: int, print_: str) -> Optional[str]:
        """The already-rendered file for this exact fix set, if it still exists."""
        entry = self._entry(song_id, print_)
        if not entry:
            return None
        if not os.path.exists(entry["path"]):
            # Rendered files live on disk under the produced directory; if one
            # was cleaned up, fall through to a fresh render.
            self._renders[song_id].pop(print_, None)
            return None
        return entry["path"]

    def remember_render(
        self,
        song_id: int,
        print_: str,
        path: str,
        notices: Optional[List[Dict[str, Any]]] = None,
        stems: Optional[List[Dict[str, str]]] = None,
        model: Optional[str] = None,
    ) -> None:
        renders = self._renders.setdefault(song_id, OrderedDict())
        renders[print_] = {
            "fingerprint": print_,
            "path": path,
            "notices": notices or [],
            "stems": stems or [],
            "model": model,
        }
        renders.move_to_end(print_)
        while len(renders) > RENDERS_PER_SONG:
            renders.popitem(last=False)

    def cached_notices(self, song_id: int, print_: str) -> List[Dict[str, Any]]:
        """What the remembered render reported doing less of than asked.

        Stored with the render rather than the job: a reused render answers a
        later request that never ran the DSP itself, and a producer accepting
        that result needs the same warning the first one got (issue #91).
        """
        return (self._entry(song_id, print_) or {}).get("notices") or []

    def cached_stems(self, song_id: int, print_: str) -> List[Dict[str, str]]:
        """The per-stem audio that went into the remembered render.

        Same reasoning as :meth:`cached_notices`: a save that reuses an earlier
        render never ran the DSP itself, so without this the stems it would keep
        for the new version exist on disk but are unknown to the request that
        saves it — and the producer would be told to re-separate a mix whose
        parts are sitting right there.
        """
        return (self._entry(song_id, print_) or {}).get("stems") or []

    def cached_model(self, song_id: int, print_: str) -> Optional[str]:
        """The separator the remembered render's stems came from.

        Travels with the stems for the same reason they do: most saves reuse a
        warm render, so without this the set kept on that path would name the
        default model rather than the one that actually produced the audio.
        """
        return (self._entry(song_id, print_) or {}).get("model")

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
            "progress": None,
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
            # A save asked for while this preview was rendering the same fixes
            # (see attach_save): the mix is what it wanted, so write it now.
            save = job.pop("_then_save", None)
            if save is not None:
                self.report(song_id, stage=STAGE_SAVING)
                result = {**result, **await save(result)}
            job["version"] = result.get("version")
            job["candidate_path"] = result.get("candidate_path")
            job["notices"] = result.get("notices") or []
            job["status"] = STATUS_COMPLETE
            logger.info(
                "Accept-fixes render complete for song %s (job %s)", song_id, job["job_id"]
            )
        except (asyncio.CancelledError, RenderCancelled):
            # Swallowed on purpose: this task is only ever cancelled by
            # cancel(), and the job's status is the whole answer to it.
            job["status"] = STATUS_CANCELLED
            logger.info("Accept-fixes render cancelled for song %s", song_id)
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
            "progress": None,
        }
        return self.status(song_id)

    def report(self, song_id: int, **progress: Any) -> None:
        """Record how far the running render has got, for the task panel.

        Fields merge into the job's ``progress``: ``stage`` (stems, remix,
        master, saving), ``done``/``total`` fix steps, ``stems_done``/
        ``stems_total``, and the ``stem`` and ``tool`` being worked on. Raises
        :class:`RenderCancelled` once the job is cancelled, which is what stops
        a render at the next step rather than at its end.
        """
        job = self._jobs.get(song_id)
        if job is None or job["status"] != STATUS_RUNNING:
            return
        if job.get("_cancelled"):
            raise RenderCancelled()
        job["progress"] = {**(job.get("progress") or {}), **progress}

    def attach_save(
        self,
        song_id: int,
        print_: str,
        save: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
    ) -> Optional[Dict[str, Any]]:
        """Turn the running render of these exact fixes into a save.

        Pressing Save while Start analysis was still rendering the same queue
        used to be refused (409). Now the save rides on the render already under
        way. Returns the job, or None when no render of this fix set is running.
        """
        job = self._jobs.get(song_id)
        if not job or job["status"] != STATUS_RUNNING or job.get("fingerprint") != print_:
            return None
        job["_then_save"] = save
        job["preview"] = False
        return self.status(song_id)

    def cancel(self, song_id: int, save_only: bool = False) -> Dict[str, Any]:
        """Stop the running render, or only the save riding on it.

        Raises ValueError when there is nothing to cancel, or when the version
        is already being written — too late to stop without half a save.
        """
        job = self._jobs.get(song_id)
        if not job or job["status"] != STATUS_RUNNING:
            raise ValueError("Nothing is rendering for this song")
        if (job.get("progress") or {}).get("stage") == STAGE_SAVING:
            raise ValueError("The version is being written and can no longer be cancelled")

        if save_only:
            job.pop("_then_save", None)
            job["preview"] = True
            return self.status(song_id)

        job["_cancelled"] = True
        task = self._tasks.get(song_id)
        if task is not None:
            # Interrupts the await the render is parked on. A tool already
            # running on a thread finishes on its own; its output goes unused.
            task.cancel()
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

        # Underscored keys are the manager's own bookkeeping (a save callback,
        # a cancel flag), not something to send to the browser.
        return {key: value for key, value in job.items() if not key.startswith("_")}

    def clear(self, song_id: int) -> None:
        """Forget a finished job, so the UI can dismiss a result or an error."""
        job = self._jobs.get(song_id)
        if job and job["status"] != STATUS_RUNNING:
            self._jobs.pop(song_id, None)


# One manager for the process, mirroring the other job runners.
accept_jobs = AcceptJobManager()
chain_cache = ChainCache()
