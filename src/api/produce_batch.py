"""Catalog-wide auto-clean batch runner (issue #29).

Turns the per-track ``/produce`` clean→version→publish flow into a single
hands-off, catalog-wide operation. A producer starts one batch; it runs in a
background task over either *all* songs or only the *not-yet-cleaned* ones,
cleans each through the existing ``auto_clean_recording`` pipeline, and publishes
each result as a new cleaned **song version** — the originals are never touched
(non-destructive, per issues #28/#30).

State is held in process memory as a single ``BatchJob`` (these production tools
have no external queue infra; the producer UI polls status). One concurrent batch
is allowed at a time. A single track's failure is recorded and the batch
continues with the rest.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from src.api.routers.produce import (
    clean_song_to_candidate,
    publish_candidate_version,
)
from database import DatabaseManager

logger = logging.getLogger("backend-api")

# Selection modes for which catalog songs a batch targets.
SELECTION_ALL = "all"
SELECTION_NOT_CLEANED = "not_cleaned"

# Per-track outcomes recorded in the job summary.
OUTCOME_SUCCEEDED = "succeeded"
OUTCOME_SKIPPED = "skipped"
OUTCOME_FAILED = "failed"


@dataclass
class TrackResult:
    song_id: int
    title: str
    outcome: str
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "song_id": self.song_id,
            "title": self.title,
            "outcome": self.outcome,
            "reason": self.reason,
        }


@dataclass
class BatchJob:
    """In-memory state for one catalog-clean batch."""

    selection: str
    aggressiveness: str
    force_reclean_all: bool
    status: str = "running"  # running | completed | failed
    total: int = 0
    completed: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    results: List[TrackResult] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "selection": self.selection,
            "aggressiveness": self.aggressiveness,
            "force_reclean_all": self.force_reclean_all,
            "total": self.total,
            "completed": self.completed,
            "succeeded": sum(r.outcome == OUTCOME_SUCCEEDED for r in self.results),
            "skipped": sum(r.outcome == OUTCOME_SKIPPED for r in self.results),
            "failed": sum(r.outcome == OUTCOME_FAILED for r in self.results),
            "results": [r.to_dict() for r in self.results],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


class BatchCleanManager:
    """Owns the single active/last catalog-clean batch and its background task."""

    def __init__(self) -> None:
        self._job: Optional[BatchJob] = None
        self._task: Optional[asyncio.Task] = None

    def is_running(self) -> bool:
        return self._job is not None and self._job.status == "running"

    def status(self) -> Optional[Dict[str, Any]]:
        return self._job.to_dict() if self._job is not None else None

    def start(
        self,
        selection: str,
        aggressiveness: str,
        force_reclean_all: bool,
        agent: BigFlavorAgent,
        db: DatabaseManager,
        rag: SongRAGSystem,
    ) -> Dict[str, Any]:
        """Kick off a batch in the background. Raises RuntimeError if one is running."""
        if self.is_running():
            raise RuntimeError("A catalog-clean batch is already running")
        if selection not in (SELECTION_ALL, SELECTION_NOT_CLEANED):
            raise ValueError(f"Unknown selection: {selection}")

        self._job = BatchJob(
            selection=selection,
            aggressiveness=aggressiveness,
            force_reclean_all=force_reclean_all,
        )
        self._task = asyncio.create_task(self._run(self._job, agent, db, rag))
        return self._job.to_dict()

    async def _run(
        self,
        job: BatchJob,
        agent: BigFlavorAgent,
        db: DatabaseManager,
        rag: SongRAGSystem,
    ) -> None:
        try:
            songs = await db.get_all_songs()
            cleaned_ids = await db.get_song_ids_with_cleaned_versions()

            # not_cleaned selection drops songs that already have a cleaned version.
            if job.selection == SELECTION_NOT_CLEANED:
                targets = [s for s in songs if s["id"] not in cleaned_ids]
            else:
                targets = list(songs)

            job.total = len(targets)
            logger.info(
                "Catalog-clean batch started: %d target songs (selection=%s, force=%s)",
                job.total,
                job.selection,
                job.force_reclean_all,
            )

            for song in targets:
                song_id = song["id"]
                title = song.get("title", "Unknown")

                # Default skips songs already cleaned; force-reclean-all overrides.
                if not job.force_reclean_all and song_id in cleaned_ids:
                    job.results.append(
                        TrackResult(song_id, title, OUTCOME_SKIPPED, "already cleaned")
                    )
                    job.completed += 1
                    continue

                await self._process_song(job, song_id, title, agent, db, rag)
                job.completed += 1

            job.status = "completed"
        except Exception as exc:  # batch-level failure (e.g. listing songs)
            logger.exception("Catalog-clean batch failed")
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = time.time()
            logger.info(
                "Catalog-clean batch finished: %s (%d/%d)",
                job.status,
                job.completed,
                job.total,
            )

    async def _process_song(
        self,
        job: BatchJob,
        song_id: int,
        title: str,
        agent: BigFlavorAgent,
        db: DatabaseManager,
        rag: SongRAGSystem,
    ) -> None:
        """Clean and publish one song; record its outcome. Never raises.

        One track's failure is caught and recorded as failed so the batch
        continues with the remaining tracks.
        """
        try:
            candidate = await clean_song_to_candidate(
                song_id, job.aggressiveness, agent, db
            )
            await publish_candidate_version(
                song_id, candidate["candidate_path"], db, rag
            )
            job.results.append(TrackResult(song_id, title, OUTCOME_SUCCEEDED))
        except Exception as exc:
            logger.warning("Batch clean failed for song %s: %s", song_id, exc)
            job.results.append(
                TrackResult(song_id, title, OUTCOME_FAILED, str(exc))
            )


# Single process-wide manager instance the routes consult.
manager = BatchCleanManager()
