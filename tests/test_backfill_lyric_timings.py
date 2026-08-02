"""Tests for the timed-lyric backfill script's selection + ledger logic.

The extraction itself is covered by tests/test_lyrics_jobs.py (the script goes
through the same ``lyrics_jobs.extract_and_store`` seam). What's script-specific
— and what a multi-hour catalog run depends on being right — is which songs get
queued on a resume, and that the failure ledger survives a bad file.
"""
import json

import pytest

import scripts.backfill_lyric_timings as backfill_script
from scripts.backfill_lyric_timings import (
    load_ledger,
    save_ledger,
    select_songs,
    summarize_coverage,
)


def _row(song_id, has_timings=False, timing_status=None, audio_source=None):
    return {
        "id": song_id,
        "title": f"Song {song_id}",
        "has_timings": has_timings,
        "timing_status": timing_status,
        "audio_source": audio_source,
        "format_version": 1 if has_timings else None,
    }


COVERAGE = [
    _row(1, has_timings=True, timing_status="current", audio_source="vocals_stem"),
    _row(2),  # never extracted
    _row(3, has_timings=True, timing_status="stale", audio_source="mix"),
    _row(4),
]


class TestSelectSongs:
    def test_defaults_to_songs_with_no_timings(self):
        """The resume case: finished songs are skipped, so a re-run continues."""
        selected = select_songs(COVERAGE, redo_all=False, redo_stale=False, song_ids=None)
        assert [row["id"] for row in selected] == [2, 4]

    def test_leaves_stale_timings_alone_by_default(self):
        """Stale means a human edited the lyrics — don't clobber that unasked."""
        selected = select_songs(COVERAGE, redo_all=False, redo_stale=False, song_ids=None)
        assert 3 not in [row["id"] for row in selected]

    def test_redo_stale_includes_them(self):
        selected = select_songs(COVERAGE, redo_all=False, redo_stale=True, song_ids=None)
        assert [row["id"] for row in selected] == [2, 3, 4]

    def test_redo_all_takes_everything(self):
        selected = select_songs(COVERAGE, redo_all=True, redo_stale=False, song_ids=None)
        assert [row["id"] for row in selected] == [1, 2, 3, 4]

    def test_explicit_song_ids_win_over_every_filter(self):
        """--song-id is an override: re-extract that song whatever its state."""
        selected = select_songs(COVERAGE, redo_all=False, redo_stale=False, song_ids=[1, 3])
        assert [row["id"] for row in selected] == [1, 3]

    def test_unknown_song_id_selects_nothing(self):
        assert select_songs(COVERAGE, False, False, song_ids=[9999]) == []

    def test_preserves_catalog_order(self):
        """A resumed run must walk the catalog the same way every time."""
        shuffled = [COVERAGE[i] for i in (3, 1, 0, 2)]
        selected = select_songs(shuffled, redo_all=True, redo_stale=False, song_ids=None)
        assert [row["id"] for row in selected] == [4, 2, 1, 3]


class TestSummarizeCoverage:
    def test_counts_each_state(self):
        summary = summarize_coverage(COVERAGE)
        assert summary["total"] == 4
        assert summary["current"] == 1
        assert summary["stale"] == 1
        assert summary["missing"] == 2

    def test_splits_by_audio_source(self):
        summary = summarize_coverage(COVERAGE)
        assert summary["from_vocals"] == 1
        assert summary["from_mix"] == 1

    def test_empty_catalog(self):
        assert summarize_coverage([])["total"] == 0


class TestLedger:
    def test_missing_ledger_starts_empty(self, tmp_path):
        assert load_ledger(tmp_path / "nope.json") == {"failures": {}}

    def test_round_trips(self, tmp_path):
        path = tmp_path / "ledger.json"
        save_ledger(path, {"failures": {"7": {"error": "No lyrics detected"}}})
        assert load_ledger(path)["failures"]["7"]["error"] == "No lyrics detected"

    def test_corrupt_ledger_starts_empty_instead_of_crashing(self, tmp_path):
        """A truncated ledger (killed mid-write) must not block the whole run."""
        path = tmp_path / "ledger.json"
        path.write_text('{"failures": {"7": ', encoding="utf-8")
        assert load_ledger(path) == {"failures": {}}

    def test_unexpected_shape_starts_empty(self, tmp_path):
        path = tmp_path / "ledger.json"
        path.write_text('["not", "a", "ledger"]', encoding="utf-8")
        assert load_ledger(path) == {"failures": {}}

    def test_save_stamps_updated_at(self, tmp_path):
        path = tmp_path / "ledger.json"
        save_ledger(path, {"failures": {}})
        assert "updated_at" in json.loads(path.read_text(encoding="utf-8"))

    def test_save_to_unwritable_path_does_not_raise(self, tmp_path):
        """Losing the ledger costs retries, not the run."""
        save_ledger(tmp_path / "no_such_dir" / "ledger.json", {"failures": {}})


class FakeDB:
    def __init__(self, coverage=None):
        self.coverage = coverage or []
        self.closed = False

    async def connect(self):
        pass

    async def close(self):
        self.closed = True

    async def ensure_song_lyric_timings_table(self):
        pass

    async def list_lyric_timing_coverage(self):
        return self.coverage


class TestEmbeddingModelGuard:
    """Storing lyrics re-embeds them; a zero-vector fallback across the whole
    catalog would silently destroy lyric search, so the run must refuse."""

    @pytest.fixture(autouse=True)
    def _fakes(self, monkeypatch):
        monkeypatch.setattr(backfill_script, "DatabaseManager", lambda: FakeDB(COVERAGE))

    def _patch_rag(self, monkeypatch, model):
        class FakeRag:
            def __init__(self, db, use_clap=False):
                self.text_embedding_model = model

        monkeypatch.setattr(backfill_script, "SongRAGSystem", FakeRag)

    @pytest.mark.asyncio
    async def test_refuses_to_run_without_a_text_embedding_model(self, monkeypatch):
        self._patch_rag(monkeypatch, None)
        assert await backfill_script.backfill(skip_confirmation=True) == 2

    @pytest.mark.asyncio
    async def test_status_still_works_without_the_model(self, monkeypatch):
        """A read-only coverage report embeds nothing, so it stays usable."""
        self._patch_rag(monkeypatch, None)
        assert await backfill_script.backfill(status_only=True) == 0

    @pytest.mark.asyncio
    async def test_dry_run_still_works_without_the_model(self, monkeypatch):
        self._patch_rag(monkeypatch, None)
        assert await backfill_script.backfill(dry_run=True) == 0
