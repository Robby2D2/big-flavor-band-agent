"""Explain, on demand, why one song came back for one query.

Search used to route through the agent so every result could carry a
"why this matched" line, which cost 2-12s per search and bought nothing else:
the agent called the same RAG function and only annotated its results. Worse,
the annotations were ungrounded — a catalogue cover of "Country Roads" was
captioned with an invented claim that Bob Dylan wrote it under a pseudonym.

So explanations moved here: generated for a single song, only when someone asks
for one, from a prompt that supplies the facts and forbids adding any.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("rag-system")

SYSTEM_PROMPT = (
    "You explain why a song matched a listener's search of a private band's "
    "catalogue. Use ONLY the facts given to you. These are unreleased home "
    "recordings, so you know nothing about them beyond those facts: never claim "
    "who wrote or released a song, when it charted, or any history. If the "
    "connection to the query is weak, say so plainly. Reply with one sentence, "
    "at most 25 words, and no preamble."
)

# Enough lyric text to ground a "it's about X" observation without turning the
# prompt into a transcript.
LYRIC_SNIPPET_CHARS = 400


def build_explain_prompt(query: str, song: Dict[str, Any], lyrics: Optional[str] = None) -> str:
    """Render the user-side prompt: the query, the song's facts, nothing else."""
    facts = [f"Title: {song.get('title') or 'unknown'}"]

    for label, key in (("Genre", "genre"), ("Mood", "mood"), ("Energy", "energy")):
        value = song.get(key)
        if value:
            facts.append(f"{label}: {value}")

    tempo = song.get("tempo_bpm")
    if tempo:
        facts.append(f"Tempo: {round(float(tempo))} BPM")

    key_sig = song.get("key")
    if key_sig:
        facts.append(f"Key: {key_sig}")

    if lyrics:
        snippet = " ".join(lyrics.split())[:LYRIC_SNIPPET_CHARS]
        if snippet:
            facts.append(f"Lyrics excerpt: {snippet}")

    joined = "\n".join(f"- {fact}" for fact in facts)
    return (
        f'The listener searched for: "{query}"\n\n'
        f"The song that matched:\n{joined}\n\n"
        "In one sentence, why does this song match that search?"
    )


def clean_explanation(text: str) -> str:
    """Trim an LLM reply down to the single sentence the UI shows.

    Small local models like to wrap the answer in quotes, prefix it with
    "Answer:", or keep going for a paragraph. None of that survives.
    """
    if not text:
        return ""

    cleaned = " ".join(text.strip().split())

    for prefix in ("Answer:", "Reason:", "Explanation:", "A:"):
        if cleaned.lower().startswith(prefix.lower()):
            cleaned = cleaned[len(prefix):].strip()

    cleaned = cleaned.strip('"').strip("'").strip()

    # Keep the first sentence only; a run-on paragraph is worse than a short line.
    for terminator in (". ", "! ", "? "):
        index = cleaned.find(terminator)
        if index != -1:
            cleaned = cleaned[: index + 1]
            break

    return cleaned.strip()
