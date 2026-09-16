"""In-depth search: an agentic retrieval loop, run as a background job.

Quick search is one semantic pass. In-depth search lets the model work the
question: decide what to look up, call the catalogue's search tools, read what
came back, look again if the evidence is thin, and finally answer citing the
songs it relied on.

It runs as a background job for the same reason the accept-fixes render does —
several model calls plus retrievals outlive an HTTP request's welcome — and it
reports each step as it happens, because with a reasoning search *what it did*
is half of what the listener wants to see.

Jobs are keyed by an opaque id rather than by song or user: a search belongs to
the tab that started it. Status is in memory; a search is cheap to re-run and
nothing about it is worth persisting past a restart.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from src.rag.deep_search import (
    EVALUATE_SYSTEM,
    MAX_CANDIDATES_IN_PROMPT,
    MAX_ROUNDS,
    PLAN_SYSTEM,
    SYNTHESIS_SYSTEM,
    build_evaluate_prompt,
    build_plan_prompt,
    build_synthesis_prompt,
    describe_tool_call,
    parse_evaluation,
    should_continue,
    summarize_candidate,
)

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

# Long enough to read the answer and come back to it; a search is cheap to re-run.
RESULT_TTL_SECONDS = 60 * 60

# Each retrieval asks for more than the tools' default of 10: the evaluator
# judges from one line per song, so a wider net costs little while a narrow one
# hides answers that were never looked at.
RESULTS_PER_SEARCH = 25

# The retrieval tools the model may choose from. Deliberately only the read
# side of the catalogue — an in-depth *search* never edits anything.
SEARCH_TOOL_NAMES = {
    "search_by_text_description",
    "search_lyrics_by_keyword",
    "search_by_tempo_range",
    "find_song_by_title",
    "search_hybrid",
}


def _search_tools(agent) -> List[Dict[str, Any]]:
    """The agent's own tool definitions, narrowed to retrieval."""
    return [t for t in agent._get_available_tools() if t.get("name") in SEARCH_TOOL_NAMES]


async def _matching_lyrics(query, songs, agent, db) -> Dict[int, str]:
    """The lyric passage of each song that best matches the question.

    Showing the *opening* of a song was the old behaviour, and for 84% of this
    catalogue the opening is the wrong quarter of the words — an evaluator asked
    "is this about the ocean?" was reading a verse that never mentions it. This
    returns the chunk that actually matched (migration 14), which is both better
    evidence and the line worth quoting back.
    """
    song_ids = [s["id"] for s in songs if s.get("id") is not None]
    if not song_ids:
        return {}

    model = getattr(agent.rag_system, "text_embedding_model", None)
    if model is None:
        return {}

    try:
        embedding = str(model.encode(query).tolist())
        return await db.best_lyric_chunks(song_ids, embedding)
    except Exception as exc:  # evidence is a nicety; never fail the search for it
        logger.warning("Could not fetch matching lyric chunks: %s", exc)
        return {}


async def run_deep_search(
    query: str,
    agent,
    db,
    emit: Callable[[str, str, str], None],
) -> Dict[str, Any]:
    """Plan, retrieve, evaluate, iterate, synthesize. Returns answer + cited songs."""
    provider = agent.llm_provider
    tools = _search_tools(agent)

    # song_id -> song, so repeated searches across rounds merge rather than
    # duplicate. Insertion order doubles as "first found".
    candidates: Dict[int, Dict[str, Any]] = {}
    evaluation: Dict[str, Any] = {"relevant_ids": [], "sufficient": True, "gap": ""}
    gap: Optional[str] = None

    for round_number in range(1, MAX_ROUNDS + 1):
        emit(
            "plan",
            "Planning" if round_number == 1 else f"Planning (round {round_number})",
            "deciding what to look up",
        )

        plan = await provider.generate_with_tools(
            messages=[{"role": "user", "content": build_plan_prompt(query, gap, round_number)}],
            tools=tools,
            system=PLAN_SYSTEM,
            temperature=0.2,
        )

        blocks = plan.get("content", []) if isinstance(plan, dict) else []
        tool_calls = [b for b in blocks if b.get("type") == "tool_use"]
        thinking = " ".join(
            b.get("text", "").strip() for b in blocks if b.get("type") == "text"
        ).strip()
        if thinking:
            emit("plan", "Plan", thinking[:300])

        if not tool_calls:
            # Nothing chosen: either it thinks it is done, or it declined to
            # search. Either way there is nothing more to retrieve.
            emit("plan", "No further searches", "answering with what is already found")
            break

        for call in tool_calls:
            name = call.get("name", "")
            args = call.get("input") or {}
            emit("retrieve", "Retrieving", describe_tool_call(name, args))
            try:
                # The model never sets a limit; the tools default to 10.
                result = await agent._call_tool(name, {"limit": RESULTS_PER_SEARCH, **args})
            except Exception as exc:  # one bad tool call must not end the search
                logger.warning("Deep search tool %s failed: %s", name, exc)
                emit("retrieve", "Search failed", f"{describe_tool_call(name, args)} — skipped")
                continue

            songs = (result or {}).get("songs") or []
            new = 0
            for song in songs:
                song_id = song.get("id")
                if song_id is not None and song_id not in candidates:
                    candidates[song_id] = song
                    new += 1
            emit("retrieve", "Found", f"{len(songs)} results, {new} new")

        emit("evaluate", "Evaluating", f"{len(candidates)} candidates so far")

        shortlist = list(candidates.values())[:MAX_CANDIDATES_IN_PROMPT]
        excerpts = await _matching_lyrics(query, shortlist, agent, db)
        lines = [summarize_candidate(s, excerpts.get(s.get("id"))) for s in shortlist]

        verdict_text = await provider.generate_response(
            messages=[{"role": "user", "content": build_evaluate_prompt(query, lines)}],
            system=EVALUATE_SYSTEM,
            temperature=0.1,
            max_tokens=600,
        )
        evaluation = parse_evaluation(verdict_text)
        emit(
            "evaluate",
            "Judged",
            f"{len(evaluation['relevant_ids'])} of {len(candidates)} look relevant",
        )

        if not should_continue(evaluation, round_number):
            break

        gap = evaluation["gap"]
        emit("refine", "Evidence is thin", gap)

    # Prefer what the model judged relevant; fall back to everything found, so a
    # search that retrieved plenty but judged badly still answers with results.
    relevant = [candidates[i] for i in evaluation.get("relevant_ids", []) if i in candidates]
    cited = relevant or list(candidates.values())[:MAX_CANDIDATES_IN_PROMPT]

    emit("synthesize", "Writing the answer", f"from {len(cited)} songs")

    shortlist = cited[:MAX_CANDIDATES_IN_PROMPT]
    excerpts = await _matching_lyrics(query, shortlist, agent, db)
    evidence = [summarize_candidate(s, excerpts.get(s.get("id"))) for s in shortlist]

    answer = await provider.generate_response(
        messages=[{"role": "user", "content": build_synthesis_prompt(query, evidence)}],
        system=SYNTHESIS_SYSTEM,
        temperature=0.3,
        max_tokens=800,
    )

    return {
        "answer": (answer or "").strip(),
        "songs": cited,
        "candidates_considered": len(candidates),
    }


class ResearchJobManager:
    """Tracks in-flight in-depth searches, keyed by an opaque job id."""

    def __init__(self) -> None:
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def start(self, query: str, run) -> Dict[str, Any]:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = {
            "job_id": job_id,
            "query": query,
            "status": STATUS_RUNNING,
            "steps": [],
            "answer": None,
            "songs": [],
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }

        def emit(kind: str, label: str, detail: str = "") -> None:
            job = self._jobs.get(job_id)
            if job is not None:
                job["steps"].append(
                    {"kind": kind, "label": label, "detail": detail, "at": time.time()}
                )

        task = asyncio.create_task(self._run(job_id, run, emit))
        self._tasks[job_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job_id, None))

        logger.info("Deep search %s started: %r", job_id, query)
        return self.status(job_id)

    async def _run(self, job_id: str, run, emit) -> None:
        job = self._jobs[job_id]
        try:
            result = await run(emit)
            job["answer"] = result.get("answer")
            job["songs"] = result.get("songs", [])
            job["candidates_considered"] = result.get("candidates_considered", 0)
            job["status"] = STATUS_COMPLETE
            logger.info("Deep search %s complete (%d songs)", job_id, len(job["songs"]))
        except Exception as exc:
            logger.exception("Deep search %s failed", job_id)
            job["status"] = STATUS_FAILED
            job["error"] = str(getattr(exc, "detail", None) or exc)
        finally:
            job["finished_at"] = time.time()

    def status(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self._jobs.get(job_id)
        if job is None:
            return None

        finished_at = job.get("finished_at")
        if finished_at is not None and time.time() - finished_at > RESULT_TTL_SECONDS:
            self._jobs.pop(job_id, None)
            return None

        return dict(job)


research_jobs = ResearchJobManager()
