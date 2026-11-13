"""Background runner for Start analysis.

A pass separates a version into stems if it has none, then runs every tool's
measurement over every stem and the full mix — minutes of work. It used to be a
loop in the browser with its findings held in page state, so leaving the produce
page lost the findings and stranded the producer with nothing but Start analysis
again (PROD-11, PROD-22). The server runs it now and the page only watches.

Progress is **in memory, keyed by version**: one pass per version at a time, the
same trade as ``accept_jobs.py`` — a restart mid-pass loses the pass, and the
producer starts it again. The *outcome* is durable, one ``song_version_analyses``
row per version, so a producer can come back to it tomorrow.

Findings are measurements of particular stems, so a row only counts while its
stem set is still the version's newest. Re-separating quietly retires it.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set

logger = logging.getLogger("backend-api")

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

STAGE_SEPARATING = "separating"
STAGE_MEASURING = "measuring"

#: The console's full-mix row, which is not a stem: its id can never collide
#: with a real one. The frontend's ``FULL_MIX_STEM_ID`` is the same number.
FULL_MIX_ROW_ID = -1
FULL_MIX_LABEL = "Full mix"

#: Measuring is CPU-bound, so running more at once only stretches each check.
ANALYZE_CONCURRENCY = 3
SEPARATION_POLL_SECONDS = 4

# Tools whose analyze() returns real measurements — the only ones worth calling
# during a pass; the rest always report ``recommended: false``
# (src/production/toolkit.py's base analyze() stub).
#
# Clicks and timing are measured on the full mix, not per stem. Separation
# smears one click across several stems, where it stops looking like one and a
# drum hit starts to; and giving each stem its own beat grid pulled the parts
# tens of milliseconds apart. Order matters: a fix chain runs in this order, so
# clicks are repaired before anything raises their level.
PER_STEM_TOOLS = ["reduce_noise", "apply_eq", "remove_hum"]
MASTER_TOOLS = [
    "remove_artifacts", "trim_silence", "apply_eq", "correct_beats",
    "normalize_audio", "apply_mastering",
]

# Demucs source names whose stem is a single line. pyin tracks one pitch at a
# time, so note detection means nothing anywhere else — and it is the most
# expensive measurement in the pass, so it is worth not spending it. ``bass`` is
# deliberately out: the detector's floor is C2 (~65 Hz), and a real bass stem
# voiced 2% of the analysis window against a vocal stem's 79%.
MONOPHONIC_SOURCES = {"vocals"}

# ...and the tagger labels (src/production/instrument_tagging.py's vocabulary)
# that name a single-line instrument, so a fiddle or a harmonica sitting inside
# ``other`` is measured too.
MONOPHONIC_INSTRUMENTS = {
    "Vocal", "Male vocal", "Female vocal", "Whistling", "Humming",
    "Fiddle / violin", "Cello", "Harmonica", "Trumpet", "Trombone",
    "Saxophone", "Flute", "Clarinet", "French horn",
}


def is_pitch_analyzable(name: str, instruments: List[Dict[str, Any]]) -> bool:
    """Whether a stem is worth measuring for tuning.

    *Any* of the stem's tags qualifying is enough, not just the highest-scoring
    one (issue #91): the tagger is multi-label precisely because one stem holds
    several instruments, and a fiddle over a pad is tagged second.
    """
    if name in MONOPHONIC_SOURCES:
        return True
    return any(tag.get("label") in MONOPHONIC_INSTRUMENTS for tag in instruments)


def stem_analysis_tools(name: str, instruments: List[Dict[str, Any]]) -> List[str]:
    """The tools a pass (or a single row's re-analysis) measures on one stem."""
    if is_pitch_analyzable(name, instruments):
        return [*PER_STEM_TOOLS, "correct_pitch"]
    return list(PER_STEM_TOOLS)


class SeparationCancelled(Exception):
    """The separation this pass was waiting on was cancelled."""


@dataclass(frozen=True)
class PassServices:
    """What a pass needs from the routes, so this module stays free of them."""

    #: One tool's verdict on one row, or None when it has nothing usable.
    measure: Callable[[int, str], Awaitable[Optional[Dict[str, Any]]]]
    #: A stem set's stems, as the API shapes them.
    list_stems: Callable[[int], Awaitable[List[Dict[str, Any]]]]
    #: Begin separating this version; returns the new stem set's id.
    start_separation: Callable[[], Awaitable[int]]
    #: Whether a stem set is really being worked on in this process.
    is_separating: Callable[[int], bool]
    #: Given the finished rows and outcomes, and whether the producer asked for
    #: the result to be saved as a version. Best-effort.
    on_complete: Callable[[List[Dict[str, Any]], List[Dict[str, Any]], bool], None]


def _newest_set(
    stem_sets: List[Dict[str, Any]], version_id: int, statuses: Set[str]
) -> Optional[Dict[str, Any]]:
    mine = [
        s for s in stem_sets
        if s["source_version_id"] == version_id and s["status"] in statuses
    ]
    return max(mine, key=lambda s: s["id"], default=None)


def _plan(stems: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The rows a pass measures: the full mix first, then each stem."""
    rows = [{"row_id": FULL_MIX_ROW_ID, "label": FULL_MIX_LABEL, "tools": MASTER_TOOLS}]
    for stem in stems:
        rows.append({
            "row_id": stem["id"],
            "label": (stem.get("display_name") or "").strip() or stem["name"],
            "tools": stem["analysis_tools"],
        })
    return rows


class AnalysisJobManager:
    """Tracks one in-flight analysis pass per version."""

    def __init__(self) -> None:
        self._jobs: Dict[int, Dict[str, Any]] = {}

    def is_running(self, version_id: int) -> bool:
        job = self._jobs.get(version_id)
        return bool(job and job["status"] == STATUS_RUNNING)

    def start(
        self,
        song_id: int,
        version_id: int,
        db: Any,
        services: PassServices,
        then_save: bool = False,
    ) -> Dict[str, Any]:
        """Begin a pass, or join the one already running (a second tab, say).

        ``then_save`` is Analyze & save: the render the pass sets off when it
        finishes is saved as a new version, not just kept for Preview. Joining a
        running pass with it turns that pass into one that saves.
        """
        if self.is_running(version_id):
            job = self._jobs[version_id]
            job["then_save"] = job["then_save"] or then_save
            return self._view(job)
        job: Dict[str, Any] = {
            "status": STATUS_RUNNING,
            "song_id": song_id,
            "source_version_id": version_id,
            "then_save": then_save,
            "stem_set_id": None,
            "stage": None,
            "separation_started_at": None,
            "rows": [],
            "error": None,
        }
        self._jobs[version_id] = job
        # Held on the job so the task isn't garbage-collected while it runs.
        job["_task"] = asyncio.create_task(self._run(job, db, services))
        logger.info("Analysis pass started for version %s", version_id)
        return self._view(job)

    async def _stems_for_pass(
        self, job: Dict[str, Any], db: Any, services: PassServices
    ) -> List[Dict[str, Any]]:
        """This version's stems, separating it first if it has none.

        Never separates over stems that already exist — making new ones is
        Separate stems' job alone. Demucs costs minutes.
        """
        version_id = job["source_version_id"]
        stem_sets = await db.list_stem_sets(job["song_id"])
        existing = _newest_set(stem_sets, version_id, {STATUS_COMPLETE})
        if existing is not None:
            stems = await services.list_stems(existing["id"])
            if stems:
                job["stem_set_id"] = existing["id"]
                return stems

        job["stage"] = STAGE_SEPARATING
        job["separation_started_at"] = time.time()
        # A set left "running" by a restart has nothing working on it, and
        # waiting for it would be waiting forever.
        in_flight = _newest_set(stem_sets, version_id, {"queued", STATUS_RUNNING})
        if in_flight is not None and services.is_separating(in_flight["id"]):
            stem_set_id = in_flight["id"]
        else:
            stem_set_id = await services.start_separation()
        job["_separating_set_id"] = stem_set_id

        while True:
            await asyncio.sleep(SEPARATION_POLL_SECONDS)
            stem_set = await db.get_stem_set(stem_set_id)
            if stem_set is None:
                raise RuntimeError("The stem set being separated has gone")
            if stem_set["status"] == STATUS_CANCELLED:
                raise SeparationCancelled()
            if stem_set["status"] == STATUS_FAILED:
                raise RuntimeError(stem_set.get("error") or "Stem separation failed")
            if stem_set["status"] == STATUS_COMPLETE:
                job.pop("_separating_set_id", None)
                stems = await services.list_stems(stem_set_id)
                if not stems:
                    raise RuntimeError("Stem separation produced no stems")
                job["stem_set_id"] = stem_set_id
                return stems

    async def _measure(
        self,
        row: Dict[str, Any],
        tool: str,
        index: int,
        slots: List[Optional[Dict[str, Any]]],
        semaphore: asyncio.Semaphore,
        services: PassServices,
    ) -> None:
        """Run one check. A tool that fails costs that check, not the pass."""
        async with semaphore:
            try:
                result = await services.measure(row["row_id"], tool)
                if result:
                    # Postgres refuses NaN in JSONB, and one bad number must
                    # not cost the whole pass its save.
                    json.dumps(result, allow_nan=False)
                    slots[index] = {"row_id": row["row_id"], "tool": tool, "result": result}
            except Exception:
                logger.exception("Analysis of %s failed on row %s", tool, row["row_id"])
        row["done"] += 1

    async def _run(self, job: Dict[str, Any], db: Any, services: PassServices) -> None:
        """Run one pass, recording its outcome. Never raises."""
        slots: List[Optional[Dict[str, Any]]] = []
        status, error = STATUS_COMPLETE, None
        try:
            plan = _plan(await self._stems_for_pass(job, db, services))
            job["stage"] = STAGE_MEASURING
            job["rows"] = [
                {"row_id": r["row_id"], "label": r["label"], "done": 0, "total": len(r["tools"])}
                for r in plan
            ]
            checks = [
                (row, tool)
                for row, planned in zip(job["rows"], plan)
                for tool in planned["tools"]
            ]
            slots.extend([None] * len(checks))
            semaphore = asyncio.Semaphore(ANALYZE_CONCURRENCY)
            await asyncio.gather(*(
                self._measure(row, tool, index, slots, semaphore, services)
                for index, (row, tool) in enumerate(checks)
            ))
        except (asyncio.CancelledError, SeparationCancelled):
            # Swallowed on purpose: this task is only ever cancelled by
            # cancel(), and the job's status is the whole answer to it.
            status = STATUS_CANCELLED
        except Exception as exc:  # a failed pass must be visible to the poller
            logger.exception("Analysis pass failed for version %s", job["source_version_id"])
            status = STATUS_FAILED
            # HTTPException carries the useful message on .detail.
            error = str(getattr(exc, "detail", None) or exc)
        await self._finish(job, slots, status, error, db, services)

    async def _finish(
        self,
        job: Dict[str, Any],
        slots: List[Optional[Dict[str, Any]]],
        status: str,
        error: Optional[str],
        db: Any,
        services: PassServices,
    ) -> None:
        version_id = job["source_version_id"]
        # A half-measured row reads as clean, so only whole rows are kept.
        finished = {row["row_id"] for row in job["rows"] if row["done"] >= row["total"]}
        outcomes = [slot for slot in slots if slot and slot["row_id"] in finished]

        # Before the status flips, so a poller that sees "complete" also finds
        # the render it set off.
        if status == STATUS_COMPLETE:
            try:
                services.on_complete(job["rows"], outcomes, job["then_save"])
            except Exception:
                logger.exception("Warm render failed to start for version %s", version_id)

        job.update(status=status, error=error, outcomes=outcomes, stage=None)
        job.pop("_separating_set_id", None)
        logger.info("Analysis pass %s for version %s", status, version_id)
        try:
            await db.save_version_analysis(
                version_id=version_id,
                song_id=job["song_id"],
                stem_set_id=job["stem_set_id"],
                status=status,
                rows=job["rows"],
                outcomes=outcomes,
                error=error,
            )
        except Exception:
            # Left in memory, so the producer still gets this pass's findings.
            logger.exception("Could not save the analysis of version %s", version_id)
            return
        if self._jobs.get(version_id) is job:
            self._jobs.pop(version_id, None)

    async def cancel(self, version_id: int, db: Any) -> Dict[str, Any]:
        """Stop the running pass (PROD-19). Whole rows already measured are kept.

        Raises ValueError when nothing is running. A separation under way is
        marked cancelled too: Demucs can't be stopped mid-pass, so it finishes
        on the GPU and ``stem_jobs`` discards what it made.
        """
        job = self._jobs.get(version_id)
        if not job or job["status"] != STATUS_RUNNING:
            raise ValueError("Nothing is being analyzed on this version")
        stem_set_id = job.get("_separating_set_id")
        if stem_set_id is not None:
            await db.set_stem_set_status(
                stem_set_id, STATUS_CANCELLED, "Cancelled by the producer"
            )
        job["_task"].cancel()
        return self._view(job)

    async def status(self, version_id: int, db: Any) -> Dict[str, Any]:
        """The running pass for a version, else its last stored outcome."""
        job = self._jobs.get(version_id)
        if job is not None:
            return self._view(job)

        idle = {"status": STATUS_IDLE, "source_version_id": version_id}
        row = await db.get_version_analysis(version_id)
        if row is None:
            return idle
        # A failed separation never had a stem set to go stale.
        if row["stem_set_id"] is not None:
            stem_sets = await db.list_stem_sets(row["song_id"])
            newest = _newest_set(stem_sets, version_id, {STATUS_COMPLETE})
            if newest is None or newest["id"] != row["stem_set_id"]:
                return idle
        return {
            "status": row["status"],
            "song_id": row["song_id"],
            "source_version_id": version_id,
            "stem_set_id": row["stem_set_id"],
            "stage": None,
            "rows": _from_jsonb(row["rows"]),
            "outcomes": _from_jsonb(row["outcomes"]),
            "error": row["error"],
        }

    async def dismiss_failure(self, version_id: int, db: Any) -> None:
        """Forget a failed pass. A failure holds no findings, so nothing is lost."""
        job = self._jobs.get(version_id)
        if job and job["status"] == STATUS_FAILED:
            self._jobs.pop(version_id, None)
        await db.delete_failed_version_analysis(version_id)

    @staticmethod
    def _view(job: Dict[str, Any]) -> Dict[str, Any]:
        # Underscored keys are the manager's own bookkeeping, not the browser's.
        return {key: value for key, value in job.items() if not key.startswith("_")}


def _from_jsonb(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


# One manager for the process, mirroring the other job runners.
analysis_jobs = AnalysisJobManager()
