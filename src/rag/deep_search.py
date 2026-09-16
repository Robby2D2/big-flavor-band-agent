"""Prompts and parsing for in-depth (agentic) catalog search.

Quick search is one semantic pass: fast, and it answers "find me songs like X"
perfectly well. In-depth search is for questions that need *working out* — which
songs fit several constraints at once, what the catalog says about a theme —
where the model decides what to look up, reads what came back, and looks again
if the evidence is thin.

Everything here is pure: prompt construction and tolerant parsing. The loop that
calls the model and the search tools lives in ``src/api/research_jobs.py``, so
the wording and the reading of replies can be tested without an LLM.

**Tolerance is the design.** A 14B local model produces good tool calls but
imperfect JSON. Every parser here degrades rather than raises: an unreadable
evaluation means "we have enough, stop looking", never a failed search.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

# How many plan -> retrieve -> evaluate rounds before answering with what we
# have. Three is enough for "refine once, then once more"; beyond that a local
# model tends to re-run the same searches rather than find anything new.
MAX_ROUNDS = 3

# Candidates carried into the evaluation prompt. Was 24, which silently dropped
# everything a second or third round found — a run that gathered 40 candidates
# only ever had 24 judged. A one-line summary each is cheap to read.
MAX_CANDIDATES_IN_PROMPT = 40

# Lyric context per candidate — a couple of lines, not a transcript.
LYRIC_SNIPPET_CHARS = 220

PLAN_SYSTEM = (
    "You search a private band's catalogue of unreleased home recordings. "
    "Decide what to look up to answer the listener's question, and call the "
    "search tools to do it. Break a question with several constraints into "
    "separate calls. "
    "Pick the right tool. Semantic search finds themes and moods. Lyric search "
    "finds songs whose words actually contain a term, and is the one that finds "
    "a subject the band sings about — semantic search alone will miss those. A "
    "question about a concrete subject (a place, a thing, a name) deserves a "
    "lyric search as well as a semantic one. "
    "Use only the tools given; you know nothing about these recordings beyond "
    "what the tools return. Do not answer yet."
)

EVALUATE_SYSTEM = (
    "You judge whether search results answer a listener's question about a "
    "private music catalogue. Use only the candidates given — never invent "
    "songs, authorship or history. "
    "Be inclusive rather than strict. Include a song that partly answers the "
    "question, or answers only one of its parts: a title or a lyric that "
    "touches the subject counts. An empty answer helps nobody — the listener "
    "would far rather see near misses. Reply with JSON only."
)

SYNTHESIS_SYSTEM = (
    "You answer questions about a private band's catalogue of unreleased home "
    "recordings, using only the evidence given. Never claim who wrote or "
    "released a song, when it charted, or any history — you know only what the "
    "evidence says. Cite songs by title. Be concise: a short paragraph, then "
    "the songs that matter. If the evidence is thin, say so plainly."
)


def build_plan_prompt(query: str, gap: Optional[str] = None, round_number: int = 1) -> str:
    """Ask the model what to look up — first pass, or again with what's missing."""
    if gap and round_number > 1:
        return (
            f'The listener asked: "{query}"\n\n'
            f"An earlier search left a gap: {gap}\n\n"
            "Search again to close it, with a **different tool** than last "
            "time — if semantic search came up short, search the lyrics for "
            "the actual words instead. Repeating the same kind of search with "
            "reworded text returns the same songs."
        )
    return (
        f'The listener asked: "{query}"\n\n'
        "Search the catalogue for what you need to answer it."
    )


def summarize_candidate(song: Dict[str, Any], lyrics: Optional[str] = None) -> str:
    """One compact evidence line per song for the evaluation/synthesis prompts."""
    parts = [f"#{song.get('id')} {song.get('title') or 'untitled'}"]

    facts = []
    for key in ("genre", "mood", "energy"):
        value = song.get(key)
        if value:
            facts.append(str(value))
    tempo = song.get("tempo_bpm")
    if tempo:
        facts.append(f"{round(float(tempo))} BPM")
    if facts:
        parts.append(f"({', '.join(facts)})")

    if lyrics:
        snippet = " ".join(str(lyrics).split())[:LYRIC_SNIPPET_CHARS]
        if snippet:
            parts.append(f'— lyrics: "{snippet}"')

    return " ".join(parts)


def build_evaluate_prompt(query: str, candidate_lines: List[str]) -> str:
    """Ask which candidates actually answer the question, and what is still missing."""
    listing = "\n".join(candidate_lines) if candidate_lines else "(nothing found)"
    return (
        f'The listener asked: "{query}"\n\n'
        f"Candidates found so far:\n{listing}\n\n"
        "Reply with JSON only, in this shape:\n"
        '{"relevant_ids": [12, 34], "sufficient": true, "gap": ""}\n\n'
        "relevant_ids: every id worth showing the listener. A song that helps "
        "answer the question in whole OR in part counts — for a two-part "
        "question, include songs that satisfy either part. Expect several.\n"
        "sufficient: true if these are enough to answer well.\n"
        "gap: if not sufficient, one sentence on what is still missing."
    )


def build_synthesis_prompt(query: str, evidence_lines: List[str]) -> str:
    """Ask for the final answer, grounded in the evidence gathered."""
    listing = "\n".join(evidence_lines) if evidence_lines else "(nothing relevant was found)"
    return (
        f'The listener asked: "{query}"\n\n'
        f"Evidence from the catalogue:\n{listing}\n\n"
        "Answer the question using only this evidence. Name the songs you are "
        "relying on. If the evidence does not really answer the question, say "
        "so rather than padding."
    )


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a reply, tolerating fences and prose."""
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return None

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    return parsed if isinstance(parsed, dict) else None


def parse_evaluation(text: str) -> Dict[str, Any]:
    """Read the evaluation reply.

    Unreadable output means "stop looking and answer with what we have": a
    malformed judgement is not a reason to keep spending the listener's time,
    and never a reason to fail the search.
    """
    parsed = _extract_json_object(text)
    if parsed is None:
        return {"relevant_ids": [], "sufficient": True, "gap": "", "parsed": False}

    raw_ids = parsed.get("relevant_ids")
    ids: List[int] = []
    if isinstance(raw_ids, list):
        for value in raw_ids:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue

    gap = parsed.get("gap")
    return {
        "relevant_ids": ids,
        "sufficient": bool(parsed.get("sufficient", True)),
        "gap": str(gap).strip() if gap else "",
        "parsed": True,
    }


def describe_tool_call(name: str, arguments: Dict[str, Any]) -> str:
    """Human-readable line for the step list — what the model chose to look up."""
    readable = {
        "search_by_text_description": "semantic search",
        "search_lyrics_by_keyword": "lyric search",
        "search_by_tempo_range": "tempo search",
        "find_song_by_title": "title lookup",
        "search_by_audio_file": "audio similarity",
        "search_hybrid": "combined search",
    }.get(name, name)

    detail = ""
    if isinstance(arguments, dict):
        for key in ("description", "query", "keyword", "title"):
            if arguments.get(key):
                detail = f'“{arguments[key]}”'
                break
        if not detail and arguments.get("min_bpm") is not None:
            detail = f"{arguments.get('min_bpm')}–{arguments.get('max_bpm')} BPM"

    return f"{readable} {detail}".strip()


def should_continue(evaluation: Dict[str, Any], round_number: int) -> bool:
    """Search again only if the model says it needs to and told us what for."""
    if round_number >= MAX_ROUNDS:
        return False
    if evaluation.get("sufficient", True):
        return False
    # Without a stated gap the next round has nothing new to go on, so it would
    # just repeat the last search.
    return bool(evaluation.get("gap"))
