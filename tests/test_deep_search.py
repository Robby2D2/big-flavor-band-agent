"""Tests for in-depth search prompts and reply parsing (src/rag/deep_search.py).

Pure — no LLM, no DB. The parsing tests matter most: a 14B local model produces
good tool calls but imperfect JSON, and the rule is that unreadable output ends
the loop gracefully rather than failing the listener's search.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.deep_search import (  # noqa: E402
    LYRIC_SNIPPET_CHARS,
    MAX_ROUNDS,
    SYNTHESIS_SYSTEM,
    build_evaluate_prompt,
    build_plan_prompt,
    build_synthesis_prompt,
    describe_tool_call,
    parse_evaluation,
    should_continue,
    summarize_candidate,
)


# --- prompts --------------------------------------------------------------

def test_first_plan_asks_for_a_search():
    prompt = build_plan_prompt("upbeat country songs about home")
    assert "upbeat country songs about home" in prompt
    assert "gap" not in prompt.lower()


def test_a_later_round_carries_the_gap_and_asks_for_something_different():
    prompt = build_plan_prompt("songs about home", gap="no tempo evidence", round_number=2)
    assert "no tempo evidence" in prompt
    assert "different" in prompt


def test_a_gap_on_the_first_round_is_ignored():
    """Round one has nothing to refine — it should read as a fresh search."""
    assert "gap" not in build_plan_prompt("x", gap="something", round_number=1).lower()


def test_synthesis_system_forbids_inventing_history():
    lowered = SYNTHESIS_SYSTEM.lower()
    assert "only" in lowered
    assert "never claim" in lowered


def test_evaluate_prompt_lists_candidates_and_asks_for_json():
    prompt = build_evaluate_prompt("q", ["#1 A", "#2 B"])
    assert "#1 A" in prompt and "#2 B" in prompt
    assert "relevant_ids" in prompt and "sufficient" in prompt


def test_prompts_say_plainly_when_nothing_was_found():
    assert "nothing found" in build_evaluate_prompt("q", [])
    assert "nothing relevant" in build_synthesis_prompt("q", [])


# --- candidate lines ------------------------------------------------------

def test_candidate_line_carries_id_title_and_facts():
    line = summarize_candidate(
        {"id": 12, "title": "Country Roads", "genre": "country",
         "mood": "nostalgic", "energy": "medium", "tempo_bpm": 103.4}
    )
    assert "#12" in line and "Country Roads" in line
    assert "country" in line and "nostalgic" in line and "103 BPM" in line


def test_candidate_line_omits_missing_facts_rather_than_saying_none():
    line = summarize_candidate({"id": 3, "title": "Untitled jam"})
    assert "None" not in line
    assert "()" not in line


def test_lyrics_are_included_but_clipped():
    line = summarize_candidate({"id": 1, "title": "T"}, lyrics="la " * 400)
    assert "lyrics:" in line
    assert len(line) < LYRIC_SNIPPET_CHARS + 120


def test_a_song_with_no_title_still_identifies_itself():
    assert "#7" in summarize_candidate({"id": 7})


# --- reading the evaluation ----------------------------------------------

def test_reads_a_clean_evaluation():
    result = parse_evaluation('{"relevant_ids": [1, 2], "sufficient": false, "gap": "no tempo"}')
    assert result["relevant_ids"] == [1, 2]
    assert result["sufficient"] is False
    assert result["gap"] == "no tempo"
    assert result["parsed"] is True


def test_reads_json_wrapped_in_a_code_fence():
    result = parse_evaluation('```json\n{"relevant_ids": [5], "sufficient": true}\n```')
    assert result["relevant_ids"] == [5]


def test_reads_json_buried_in_prose():
    result = parse_evaluation('Sure! {"relevant_ids": [9], "sufficient": true} Hope that helps.')
    assert result["relevant_ids"] == [9]


def test_unreadable_output_ends_the_loop_instead_of_failing():
    """A malformed judgement must not cost the listener their search."""
    result = parse_evaluation('I think songs 1 and 2 are good?')
    assert result["sufficient"] is True
    assert result["relevant_ids"] == []
    assert result["parsed"] is False


def test_empty_output_ends_the_loop():
    assert parse_evaluation("")["sufficient"] is True


def test_non_numeric_ids_are_dropped_not_fatal():
    result = parse_evaluation('{"relevant_ids": [1, "two", null, 3], "sufficient": true}')
    assert result["relevant_ids"] == [1, 3]


def test_string_ids_are_coerced():
    assert parse_evaluation('{"relevant_ids": ["12"], "sufficient": true}')["relevant_ids"] == [12]


def test_a_json_array_is_not_mistaken_for_an_evaluation():
    assert parse_evaluation('[1, 2, 3]')["parsed"] is False


# --- loop control ---------------------------------------------------------

def test_stops_when_the_model_is_satisfied():
    assert should_continue({"sufficient": True, "gap": "x"}, 1) is False


def test_searches_again_when_evidence_is_thin_and_a_gap_is_named():
    assert should_continue({"sufficient": False, "gap": "no tempo evidence"}, 1) is True


def test_does_not_loop_without_a_stated_gap():
    """With nothing to change, the next round repeats the last search."""
    assert should_continue({"sufficient": False, "gap": ""}, 1) is False


def test_stops_at_the_round_limit():
    assert should_continue({"sufficient": False, "gap": "more"}, MAX_ROUNDS) is False


# --- step descriptions ----------------------------------------------------

def test_tool_calls_read_as_plain_english():
    assert describe_tool_call(
        "search_lyrics_by_keyword", {"keyword": "home"}
    ) == 'lyric search “home”'
    assert describe_tool_call(
        "search_by_tempo_range", {"min_bpm": 120, "max_bpm": 130}
    ) == "tempo search 120–130 BPM"


def test_an_unknown_tool_still_describes_itself():
    assert "mystery_tool" in describe_tool_call("mystery_tool", {})


def test_a_tool_call_with_no_useful_argument_has_no_trailing_space():
    assert describe_tool_call("search_by_text_description", {}) == "semantic search"
