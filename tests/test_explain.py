"""Tests for on-demand match explanations (src/rag/explain.py).

Pure prompt-building and reply-cleaning — no LLM call. The prompt is the whole
defence against the ungrounded commentary this replaced (a catalogue cover of
"Country Roads" captioned with an invented claim about Bob Dylan writing it),
so what it does and does not contain is worth asserting.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.explain import (  # noqa: E402
    LYRIC_SNIPPET_CHARS,
    SYSTEM_PROMPT,
    build_explain_prompt,
    clean_explanation,
)

SONG = {
    "title": "Country Roads - Christopher and Tori Santer",
    "genre": "country",
    "mood": "nostalgic",
    "energy": "medium",
    "tempo_bpm": 103.4,
    "key": "A",
}


# --- the prompt ------------------------------------------------------------

def test_prompt_carries_the_query_and_the_song_facts():
    prompt = build_explain_prompt("upbeat country song about home", SONG)

    assert "upbeat country song about home" in prompt
    assert "Country Roads" in prompt
    assert "country" in prompt
    assert "nostalgic" in prompt
    assert "103 BPM" in prompt


def test_system_prompt_forbids_inventing_history():
    """The failure this replaced was a confident, invented authorship claim."""
    lowered = SYSTEM_PROMPT.lower()

    assert "only" in lowered
    assert "never claim" in lowered
    assert "wrote" in lowered


def test_missing_fields_are_omitted_not_offered_as_none():
    prompt = build_explain_prompt("anything", {"title": "Untitled jam"})

    assert "Untitled jam" in prompt
    assert "None" not in prompt
    assert "Genre:" not in prompt


def test_unknown_title_is_labelled_not_blank():
    assert "unknown" in build_explain_prompt("anything", {})


def test_lyrics_are_included_but_truncated():
    lyrics = "la " * 2000
    prompt = build_explain_prompt("anything", SONG, lyrics)

    assert "Lyrics excerpt:" in prompt
    assert len(prompt) < LYRIC_SNIPPET_CHARS + 600


def test_lyrics_whitespace_is_collapsed():
    prompt = build_explain_prompt("anything", SONG, "line one\n\n\n   line two")

    assert "line one line two" in prompt


def test_absent_lyrics_add_no_section():
    assert "Lyrics excerpt" not in build_explain_prompt("anything", SONG)
    assert "Lyrics excerpt" not in build_explain_prompt("anything", SONG, "")


# --- cleaning the reply ----------------------------------------------------

def test_plain_sentence_passes_through():
    assert clean_explanation("It is a country song about home.") == "It is a country song about home."


def test_strips_a_leading_label():
    assert clean_explanation("Answer: It matches the genre.") == "It matches the genre."
    assert clean_explanation("Reason: It matches.") == "It matches."


def test_strips_wrapping_quotes():
    assert clean_explanation('"It matches the genre."') == "It matches the genre."


def test_keeps_only_the_first_sentence():
    reply = "It is a country song. It also has a nostalgic mood. And more besides."
    assert clean_explanation(reply) == "It is a country song."


def test_collapses_whitespace_and_newlines():
    assert clean_explanation("  It   matches\nthe genre.  ") == "It matches the genre."


def test_handles_a_label_wrapped_in_quotes():
    assert clean_explanation('Answer: "It matches."') == "It matches."


def test_empty_reply_stays_empty():
    """The route turns this into a 502 rather than showing a blank tooltip."""
    assert clean_explanation("") == ""
    assert clean_explanation("   ") == ""
