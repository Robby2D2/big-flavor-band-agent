"""Multi-label mood and genre tags.

A song carries one mood and one genre in its own columns, because the derive
scripts ask the model to choose exactly one. That is fine for a badge and wrong
for a question: "about water and feels calm" needs a song to be able to be two
things at once.

Pure parsing and validation. ``scripts/backfill_song_tags.py`` does the asking.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from src.rag.derive_energy_mood import MOOD_LABELS
from src.rag.derive_genre import GENRE_LABELS

# Enough to describe a song honestly; more and the model starts listing the
# whole vocabulary and the labels stop meaning anything.
MAX_MOODS = 3
MAX_GENRES = 2

SYSTEM_PROMPT = (
    "You are a music analyst. Given a song's metadata and lyrics, list every "
    "mood and genre that genuinely applies — most songs are more than one thing. "
    "Respond with ONLY a JSON object and nothing else, in the form "
    f'{{"moods": [...], "genres": [...]}}. Moods must come from {MOOD_LABELS}. '
    f"Genres must come from {GENRE_LABELS}. Give at most {MAX_MOODS} moods and "
    f"{MAX_GENRES} genres, most characteristic first. Include a label only if it "
    "really fits — a wrong tag is worse than a missing one."
)


def _valid(values: Any, vocabulary: List[str], limit: int) -> List[str]:
    """Keep known labels, in order, without duplicates, up to the limit."""
    if not isinstance(values, list):
        return []

    allowed = {v.lower(): v for v in vocabulary}
    kept: List[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        canonical = allowed.get(value.strip().lower())
        if canonical and canonical not in kept:
            kept.append(canonical)
        if len(kept) >= limit:
            break
    return kept


def parse_tags(text: str) -> Dict[str, List[str]]:
    """Read a tagging reply, dropping anything outside the vocabularies.

    Unreadable output yields empty lists: the song keeps its primary label and
    simply gains nothing, which is the right outcome for a tagging pass that is
    purely additive.
    """
    if not text:
        return {"moods": [], "genres": []}

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {"moods": [], "genres": []}

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"moods": [], "genres": []}

    if not isinstance(parsed, dict):
        return {"moods": [], "genres": []}

    return {
        "moods": _valid(parsed.get("moods"), MOOD_LABELS, MAX_MOODS),
        "genres": _valid(parsed.get("genres"), GENRE_LABELS, MAX_GENRES),
    }


def build_tagging_prompt(song: Dict[str, Any], lyrics: Optional[str] = None) -> str:
    """The per-song prompt: what we already believe, plus its words."""
    facts = [f"Title: {song.get('title') or 'unknown'}"]
    for label, key in (("Current genre", "genre"), ("Current mood", "mood"),
                       ("Energy", "energy"), ("Key", "key")):
        value = song.get(key)
        if value:
            facts.append(f"{label}: {value}")
    tempo = song.get("tempo_bpm")
    if tempo:
        facts.append(f"Tempo: {round(float(tempo))} BPM")

    if lyrics:
        snippet = " ".join(str(lyrics).split())[:1500]
        if snippet:
            facts.append(f"Lyrics: {snippet}")

    return "\n".join(facts) + "\n\nList the moods and genres that apply."
