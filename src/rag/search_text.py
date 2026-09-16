"""Text preparation for catalog search.

Two pure helpers, kept free of DB and model so the parts that decide *what*
gets compared are unit-testable on their own:

- ``build_metadata_text`` — the sentence embedded alongside each song's lyrics.
  Until 2026-09-15 only lyrics were embedded, so a query like "melancholic
  country" could only match songs whose *words* happened to contain those terms;
  a song's own genre and mood were invisible to semantic search.
- ``tokenize_query`` — splits a query for the keyword branch, which previously
  matched the entire query as one ``ILIKE '%…%'`` pattern and so could never
  match anything with more than one word in it.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

# Words that describe the *request* rather than the music. Dropped from the
# keyword branch only — the semantic branch still embeds the full query, so
# nothing is lost from the meaning.
STOP_WORDS = frozenset({
    "a", "an", "and", "any", "anything", "are", "about", "for", "find", "from",
    "get", "give", "in", "is", "it", "like", "me", "music", "my", "of", "on",
    "or", "play", "please", "show", "some", "something", "song", "songs",
    "sound", "sounds", "that", "the", "these", "this", "those", "to", "track",
    "tracks", "want", "with",
})

MIN_TOKEN_LENGTH = 2


def build_metadata_text(song: Dict[str, Any]) -> str:
    """Render a song's metadata as the sentence to embed.

    Labelled natural language ("Genre: country.") rather than bare values, since
    the sentence-transformer was trained on prose and the labels give the values
    context. Missing fields are skipped rather than rendered as "None", which
    would otherwise put the same noise token on every sparse song.
    """
    parts: List[str] = []

    title = (song.get("title") or "").strip()
    if title:
        parts.append(title)

    # Every label that applies, not just the primary one (migration 15): a song
    # that is both melancholic and calm should be findable as either.
    for label, key, extra_key in (
        ("Genre", "genre", "genres"),
        ("Mood", "mood", "moods"),
        ("Energy", "energy", None),
    ):
        values = []
        primary = song.get(key)
        if primary and str(primary).strip():
            values.append(str(primary).strip())
        if extra_key:
            for tag in song.get(extra_key) or []:
                tag = str(tag).strip()
                if tag and tag.lower() not in {v.lower() for v in values}:
                    values.append(tag)
        if values:
            suffix = " energy" if key == "energy" else ""
            parts.append(f"{label}: {', '.join(values)}{suffix}")

    tempo = song.get("tempo_bpm")
    if tempo:
        parts.append(f"Tempo: {round(float(tempo))} BPM")

    key_sig = song.get("key")
    if key_sig:
        key_sig = str(key_sig).strip()
        if key_sig:
            parts.append(f"Key: {key_sig}")

    return ". ".join(parts) + "." if parts else ""


def tokenize_query(query: str) -> List[str]:
    """Split a query into distinct, meaningful lowercase keyword tokens.

    Order is preserved so the result reads like the query; duplicates and
    request-describing stop words are dropped. Returns an empty list when the
    query carries no keyword signal, which the caller treats as "semantic only"
    rather than as "match everything".
    """
    if not query:
        return []

    tokens: List[str] = []
    seen = set()

    # Keep apostrophes inside words ("don't" must not become "don", which would
    # substring-match London and Donald), but split on underscore: `_` is a
    # single-character wildcard in ILIKE and would match more than was typed.
    for raw in re.split(r"[^\w']+|_+", query.lower()):
        token = raw.strip("'")
        if len(token) < MIN_TOKEN_LENGTH or token in STOP_WORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)

    return tokens
