"""Tests for the in-depth search job manager (src/api/research_jobs.py).

No LLM and no DB — a fake run coroutine stands in for the loop. What matters is
the bookkeeping the page polls: steps accumulate while it works, a failure is
visible rather than silent, and an unknown or expired job reads as gone.
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.research_jobs import (  # noqa: E402
    RESULT_TTL_SECONDS,
    SEARCH_TOOL_NAMES,
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_RUNNING,
    ResearchJobManager,
)


@pytest.mark.asyncio
async def test_a_search_runs_and_reports_its_answer():
    manager = ResearchJobManager()

    async def run(emit):
        emit("plan", "Planning", "deciding")
        emit("retrieve", "Retrieving", "lyric search")
        return {"answer": "Three songs mention rivers.", "songs": [{"id": 1}],
                "candidates_considered": 12}

    started = manager.start("songs about rivers", run)
    assert started["status"] == STATUS_RUNNING
    assert started["query"] == "songs about rivers"

    await asyncio.sleep(0.05)

    done = manager.status(started["job_id"])
    assert done["status"] == STATUS_COMPLETE
    assert done["answer"] == "Three songs mention rivers."
    assert done["songs"] == [{"id": 1}]
    assert done["candidates_considered"] == 12


@pytest.mark.asyncio
async def test_steps_are_visible_while_it_is_still_working():
    """The step list is the point of an in-depth search — it must stream, not
    appear all at once at the end."""
    manager = ResearchJobManager()
    release = asyncio.Event()

    async def run(emit):
        emit("plan", "Planning", "deciding what to look up")
        emit("retrieve", "Retrieving", "semantic search")
        await release.wait()
        return {"answer": "done", "songs": []}

    started = manager.start("q", run)
    await asyncio.sleep(0.05)

    mid = manager.status(started["job_id"])
    assert mid["status"] == STATUS_RUNNING
    assert [s["label"] for s in mid["steps"]] == ["Planning", "Retrieving"]

    release.set()
    await asyncio.sleep(0.05)
    assert manager.status(started["job_id"])["status"] == STATUS_COMPLETE


@pytest.mark.asyncio
async def test_a_failure_is_visible_with_its_reason():
    manager = ResearchJobManager()

    async def run(emit):
        emit("plan", "Planning", "")
        raise RuntimeError("the model refused")

    started = manager.start("q", run)
    await asyncio.sleep(0.05)

    status = manager.status(started["job_id"])
    assert status["status"] == STATUS_FAILED
    assert "the model refused" in status["error"]
    # Whatever it managed before failing is still worth showing.
    assert len(status["steps"]) == 1


@pytest.mark.asyncio
async def test_two_searches_do_not_share_state():
    manager = ResearchJobManager()

    async def run(emit):
        emit("plan", "Planning", "")
        return {"answer": "a", "songs": []}

    first = manager.start("one", run)
    second = manager.start("two", run)
    await asyncio.sleep(0.05)

    assert first["job_id"] != second["job_id"]
    assert manager.status(first["job_id"])["query"] == "one"
    assert manager.status(second["job_id"])["query"] == "two"


def test_an_unknown_job_reads_as_gone():
    assert ResearchJobManager().status("no-such-job") is None


@pytest.mark.asyncio
async def test_a_stale_result_expires(monkeypatch):
    manager = ResearchJobManager()

    async def run(emit):
        return {"answer": "a", "songs": []}

    started = manager.start("q", run)
    await asyncio.sleep(0.05)
    assert manager.status(started["job_id"]) is not None

    later = time.time() + RESULT_TTL_SECONDS + 60

    class FrozenClock:
        @staticmethod
        def time():
            return later

    monkeypatch.setattr("src.api.research_jobs.time", FrozenClock)
    assert manager.status(started["job_id"]) is None


def test_the_model_is_offered_only_read_tools():
    """An in-depth *search* must never be able to edit the catalogue."""
    assert all(name.startswith(("search_", "find_")) for name in SEARCH_TOOL_NAMES)
    assert not any("apply" in n or "clean" in n or "delete" in n for n in SEARCH_TOOL_NAMES)
