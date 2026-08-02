"""Tests for stem instrument tagging.

Demucs' source list is fixed by the model, so a banjo lands in "other" and the
only way to name it is to tag the stem after the fact. The pieces worth testing
are the pure ones — mapping AudioSet's comma-separated display names onto a
producer-facing vocabulary, and collapsing raw per-class scores into a ranked
list — plus the router's rename validation.

Assert-based, no model download, no live DB — matching the FakeDB pattern in
test_produce_stem_tools.py.
"""

import pytest
from fastapi import HTTPException

from src.api.routers import produce
from src.production import instrument_tagging as tagging


# ---- build_label_index ----

def test_build_label_index_matches_audioset_alias_lists():
    """AudioSet display names are comma-separated aliases: "Violin, fiddle"
    must match on either side, since our vocabulary lists both."""
    index = tagging.build_label_index(
        {0: "Violin, fiddle", 1: "Banjo", 2: "Steel guitar, slide guitar"}
    )
    assert index == {
        0: "Fiddle / violin",
        1: "Banjo",
        2: "Steel / slide guitar",
    }


def test_build_label_index_ignores_non_instrument_classes():
    """AudioSet is 527 classes of everything; only the vocabulary survives."""
    index = tagging.build_label_index(
        {0: "Banjo", 1: "Vehicle horn, car horn, honking", 2: "Sneeze"}
    )
    assert index == {0: "Banjo"}


# ---- summarize_scores ----

def test_summarize_scores_ranks_and_thresholds():
    label_index = {0: "Banjo", 1: "Fiddle / violin", 2: "Piano"}
    result = tagging.summarize_scores(
        {0: 0.42, 1: 0.81, 2: 0.02}, label_index, min_score=0.1, max_labels=4
    )
    # Strongest first, and the sub-threshold piano is dropped entirely.
    assert [r["label"] for r in result] == ["Fiddle / violin", "Banjo"]
    assert result[0]["score"] == 0.81


def test_summarize_scores_collapses_classes_sharing_a_name():
    """Three AudioSet organ classes are one instrument to a producer — the
    strongest wins rather than the name appearing three times."""
    label_index = {0: "Organ", 1: "Organ", 2: "Organ"}
    result = tagging.summarize_scores({0: 0.2, 1: 0.7, 2: 0.4}, label_index)
    assert result == [{"label": "Organ", "score": 0.7}]


def test_summarize_scores_caps_label_count():
    label_index = {0: "Banjo", 1: "Mandolin", 2: "Piano", 3: "Cello", 4: "Flute"}
    result = tagging.summarize_scores(
        {0: 0.9, 1: 0.8, 2: 0.7, 3: 0.6, 4: 0.5}, label_index, max_labels=3
    )
    assert [r["label"] for r in result] == ["Banjo", "Mandolin", "Piano"]


def test_summarize_scores_ignores_unmapped_classes():
    """A class index outside the instrument vocabulary contributes nothing."""
    assert tagging.summarize_scores({99: 0.99}, {0: "Banjo"}) == []


# ---- summarize_for_display ----

def test_summarize_for_display_distinguishes_silent_from_untagged():
    # An empty Demucs stem (the band has no piano) is a real answer, not a
    # failure, and must not read the same as "we never looked".
    assert tagging.summarize_for_display(None) == "not identified"
    assert tagging.summarize_for_display({"silent": True, "instruments": []}) == "silent"
    assert (
        tagging.summarize_for_display({"silent": False, "instruments": []})
        == "nothing recognised"
    )
    assert (
        tagging.summarize_for_display(
            {"silent": False, "instruments": [{"label": "Banjo"}, {"label": "Mandolin"}]}
        )
        == "Banjo · Mandolin"
    )


# ---- _stem_view ----

def test_stem_view_keeps_source_name_alongside_producer_label():
    """Relabelling a stem must not lose what Demucs actually produced — the fix
    tools still reason about the source stem."""
    view = produce._stem_view(
        {
            "id": 3,
            "name": "other",
            "display_name": "Banjo",
            "instrument_tags": {
                "instruments": [{"label": "Banjo", "score": 0.7}],
                "silent": False,
            },
            "tagged_at": "2026-08-02T00:00:00",
        }
    )
    assert view["name"] == "other"
    assert view["display_name"] == "Banjo"
    assert view["instruments"] == [{"label": "Banjo", "score": 0.7}]
    assert view["silent"] is False
    assert view["tagged"] is True


def test_stem_view_parses_jsonb_returned_as_text():
    """asyncpg hands JSONB back as a string unless a codec is registered."""
    view = produce._stem_view(
        {
            "id": 4,
            "name": "piano",
            "display_name": None,
            "instrument_tags": '{"instruments": [], "silent": true}',
            "tagged_at": "2026-08-02T00:00:00",
        }
    )
    assert view["silent"] is True
    assert view["instruments"] == []


def test_stem_view_untagged_stem_reports_not_tagged():
    view = produce._stem_view(
        {"id": 5, "name": "vocals", "display_name": None, "instrument_tags": None,
         "tagged_at": None}
    )
    assert view["tagged"] is False
    assert view["instruments"] == []
    assert view["silent"] is False


# ---- rename_stem ----

class FakeStemDB:
    """In-memory stand-in for the two stem methods the rename route touches."""

    def __init__(self, stems=None):
        self.stems = stems or {}
        self.renames = []

    async def set_stem_display_name(self, stem_id, display_name):
        self.renames.append((stem_id, display_name))
        stem = self.stems.get(stem_id)
        if stem is None:
            return None
        stem = {**stem, "display_name": display_name}
        self.stems[stem_id] = stem
        return stem


def _stem_row(stem_id=1, name="other"):
    return {
        "id": stem_id,
        "name": name,
        "display_name": None,
        "instrument_tags": None,
        "tagged_at": None,
    }


@pytest.mark.asyncio
async def test_rename_stem_sets_display_name():
    db = FakeStemDB({1: _stem_row()})
    result = await produce.rename_stem(
        1, produce.RenameStemRequest(display_name="  Banjo  "), db=db, _role="editor"
    )
    assert db.renames == [(1, "Banjo")]
    assert result["stem"]["display_name"] == "Banjo"
    assert result["stem"]["name"] == "other"


@pytest.mark.asyncio
async def test_rename_stem_empty_name_clears_override():
    """An empty name means "go back to what Demucs called it", stored as NULL —
    not an empty-string label that renders as a blank row."""
    db = FakeStemDB({1: _stem_row()})
    await produce.rename_stem(
        1, produce.RenameStemRequest(display_name="   "), db=db, _role="editor"
    )
    assert db.renames == [(1, None)]


@pytest.mark.asyncio
async def test_rename_stem_rejects_overlong_name():
    db = FakeStemDB({1: _stem_row()})
    with pytest.raises(HTTPException) as exc_info:
        await produce.rename_stem(
            1, produce.RenameStemRequest(display_name="x" * 65), db=db, _role="editor"
        )
    assert exc_info.value.status_code == 400
    assert db.renames == []


@pytest.mark.asyncio
async def test_rename_stem_missing_stem_404():
    db = FakeStemDB()
    with pytest.raises(HTTPException) as exc_info:
        await produce.rename_stem(
            404, produce.RenameStemRequest(display_name="Banjo"), db=db, _role="editor"
        )
    assert exc_info.value.status_code == 404
