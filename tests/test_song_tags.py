"""Tests for multi-label tag parsing (src/rag/song_tags.py).

The tagging pass is purely additive — a song keeps its primary label and gains
others — so the rule is that anything unreadable or outside the vocabulary
yields nothing rather than corrupting the labels.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.derive_energy_mood import MOOD_LABELS  # noqa: E402
from src.rag.song_tags import (  # noqa: E402
    MAX_GENRES,
    MAX_MOODS,
    build_tagging_prompt,
    parse_tags,
)


def test_reads_moods_and_genres():
    tags = parse_tags('{"moods": ["calm", "nostalgic"], "genres": ["folk"]}')
    assert tags["moods"] == ["calm", "nostalgic"]
    assert tags["genres"] == ["folk"]


def test_drops_labels_outside_the_vocabulary():
    """A wrong tag is worse than a missing one — it makes the column unfilterable."""
    tags = parse_tags('{"moods": ["calm", "vibey", "chill"], "genres": ["skiffle"]}')
    assert tags["moods"] == ["calm"]
    assert tags["genres"] == []


def test_is_case_insensitive_and_canonicalises():
    assert parse_tags('{"moods": ["CALM"], "genres": ["Folk"]}') == {
        "moods": ["calm"], "genres": ["folk"]
    }


def test_dedupes():
    assert parse_tags('{"moods": ["calm", "Calm", "calm"]}')["moods"] == ["calm"]


def test_caps_the_number_of_labels():
    many = '{"moods": %s, "genres": ["folk","rock","pop","blues"]}' % str(MOOD_LABELS).replace("'", '"')
    tags = parse_tags(many)
    assert len(tags["moods"]) <= MAX_MOODS
    assert len(tags["genres"]) <= MAX_GENRES


def test_order_is_preserved_so_the_first_is_the_most_characteristic():
    assert parse_tags('{"moods": ["dark", "calm"]}')["moods"] == ["dark", "calm"]


def test_unreadable_output_yields_no_tags_rather_than_failing():
    assert parse_tags("I think it's calm and folky") == {"moods": [], "genres": []}
    assert parse_tags("") == {"moods": [], "genres": []}
    assert parse_tags("[1,2,3]") == {"moods": [], "genres": []}


def test_reads_json_in_a_code_fence():
    assert parse_tags('```json\n{"moods": ["calm"]}\n```')["moods"] == ["calm"]


def test_non_string_entries_are_skipped():
    assert parse_tags('{"moods": [null, 3, "calm"]}')["moods"] == ["calm"]


def test_prompt_carries_what_we_already_believe_plus_the_words():
    prompt = build_tagging_prompt(
        {"title": "River", "genre": "folk", "mood": "calm", "tempo_bpm": 92.4},
        lyrics="down by the river",
    )
    assert "River" in prompt and "folk" in prompt and "92 BPM" in prompt
    assert "down by the river" in prompt


def test_prompt_omits_missing_facts():
    assert "None" not in build_tagging_prompt({"title": "Untitled"})
