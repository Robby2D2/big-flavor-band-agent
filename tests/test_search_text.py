"""Tests for the text prepared for catalog search (src/rag/search_text.py).

Pure functions — no DB, no embedding model. These cover the two inputs that
decide what search can possibly match: the metadata sentence embedded per song,
and how a query is split for the keyword branch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.search_text import (  # noqa: E402
    STOP_WORDS,
    build_metadata_text,
    tokenize_query,
)

FULL_SONG = {
    "title": "Country Roads - Christopher and Tori Santer",
    "genre": "country",
    "mood": "nostalgic",
    "energy": "medium",
    "tempo_bpm": 103.4,
    "key": "A",
}


# --- the sentence embedded per song ---------------------------------------

def test_metadata_text_carries_every_searchable_field():
    text = build_metadata_text(FULL_SONG)

    assert "Country Roads" in text
    assert "country" in text
    assert "nostalgic" in text
    assert "medium energy" in text
    assert "103 BPM" in text
    assert "Key: A" in text


def test_metadata_text_rounds_tempo():
    assert "103 BPM" in build_metadata_text(FULL_SONG)
    assert "104 BPM" in build_metadata_text({**FULL_SONG, "tempo_bpm": 103.6})


def test_missing_fields_are_omitted_not_rendered_as_none():
    """A sparse song must not carry the same 'None' noise token as every other."""
    text = build_metadata_text({"title": "Untitled jam", "genre": None, "mood": "",
                                "energy": None, "tempo_bpm": None, "key": None})

    assert text == "Untitled jam."
    assert "None" not in text
    assert "Genre" not in text


def test_zero_tempo_is_not_rendered():
    assert "BPM" not in build_metadata_text({"title": "X", "tempo_bpm": 0})


def test_a_song_with_nothing_yields_nothing():
    assert build_metadata_text({}) == ""
    assert build_metadata_text({"title": "   "}) == ""


def test_whitespace_around_values_is_trimmed():
    text = build_metadata_text({"title": "  Padded  ", "genre": "  folk  "})
    assert text == "Padded. Genre: folk."


# --- how a query is split for the keyword branch ---------------------------

def test_tokenizes_a_natural_query():
    assert tokenize_query("upbeat country song about home") == ["upbeat", "country", "home"]


def test_drops_words_that_describe_the_request_not_the_music():
    assert tokenize_query("find me some songs") == []
    assert "song" in STOP_WORDS


def test_preserves_order_and_drops_duplicates():
    assert tokenize_query("punk punk PUNK rock") == ["punk", "rock"]


def test_is_case_insensitive():
    assert tokenize_query("PUNK Rock") == ["punk", "rock"]


def test_strips_punctuation():
    assert tokenize_query("punk, rock & roll!") == ["punk", "rock", "roll"]


def test_keeps_apostrophes_inside_words():
    """'don't' must not become 'don', which substring-matches London and Donald."""
    assert tokenize_query("don't stop") == ["don't", "stop"]


def test_splits_on_underscore_so_no_token_carries_an_ilike_wildcard():
    """`_` matches any single character in ILIKE — a token must never contain one."""
    tokens = tokenize_query("rock_n_roll")

    assert tokens == ["rock", "roll"]
    assert all("_" not in token for token in tokens)


def test_drops_single_characters():
    assert tokenize_query("a b punk") == ["punk"]


def test_empty_query_yields_no_tokens():
    """An empty token list means 'semantic only', never 'match everything'."""
    assert tokenize_query("") == []
    assert tokenize_query("   ") == []
    assert tokenize_query("the of and") == []
