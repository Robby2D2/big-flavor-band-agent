"""Assert-based tests for the producer catalog + version-level clean (issue #49).

Exercise the pure routing/shaping helpers in src/api/routers/produce.py without a
live database or any LLM call: the catalog-row view, the source-aware dedup key,
and the version-aware source-path resolver (with a fake DB and a real temp file).
"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.routers import produce


def test_catalog_song_view_marks_cleaned_and_surfaces_columns():
    song = {
        "id": 5,
        "title": "Big Flavor Jam",
        "genre": "Funk",
        "tempo_bpm": 118.4,
        "duration_seconds": 212,
    }
    view = produce._catalog_song_view(song, cleaned_ids={5, 9})
    assert view == {
        "id": 5,
        "title": "Big Flavor Jam",
        "genre": "Funk",
        "tempo_bpm": 118.4,
        "duration_seconds": 212,
        "cleaned": True,
    }


def test_catalog_song_view_not_cleaned_and_missing_title():
    song = {"id": 7}
    view = produce._catalog_song_view(song, cleaned_ids={5})
    assert view["cleaned"] is False
    assert view["title"] == "Unknown"
    assert view["genre"] is None


def _cleanup_result():
    return {
        "aggressiveness": "moderate",
        "steps_applied": [{"step": "trim"}, {"step": "normalize"}],
    }


def test_dedup_key_distinguishes_source_version():
    """Re-cleaning a different version with identical steps gets a distinct key."""
    from_original = produce._autoclean_dedup_key(_cleanup_result(), None)
    from_version = produce._autoclean_dedup_key(_cleanup_result(), 42)
    assert from_original != from_version
    assert from_original.startswith("original|")
    assert from_version.startswith("v42|")
    # Same source + same steps/intensity is stable (so a re-run replaces in place).
    assert from_version == produce._autoclean_dedup_key(_cleanup_result(), 42)


class FakeDB:
    """Minimal DatabaseManager stand-in returning a canned version row."""

    def __init__(self, version):
        self._version = version

    async def get_song_version(self, version_id):
        if self._version and self._version["id"] == version_id:
            return self._version
        return None


@pytest.mark.asyncio
async def test_resolve_clean_source_path_uses_version_audio(tmp_path):
    audio = tmp_path / "5_cleaned.wav"
    audio.write_bytes(b"RIFF")
    db = FakeDB({"id": 3, "song_id": 5, "audio_path": str(audio)})

    resolved = await produce._resolve_clean_source_path(5, 3, db)
    assert resolved == Path(str(audio))


@pytest.mark.asyncio
async def test_resolve_clean_source_path_rejects_foreign_version(tmp_path):
    audio = tmp_path / "9_cleaned.wav"
    audio.write_bytes(b"RIFF")
    # Version 3 belongs to song 9, not the requested song 5.
    db = FakeDB({"id": 3, "song_id": 9, "audio_path": str(audio)})

    with pytest.raises(HTTPException) as exc:
        await produce._resolve_clean_source_path(5, 3, db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_clean_source_path_missing_file_is_404(tmp_path):
    db = FakeDB({"id": 3, "song_id": 5, "audio_path": str(tmp_path / "gone.wav")})

    with pytest.raises(HTTPException) as exc:
        await produce._resolve_clean_source_path(5, 3, db)
    assert exc.value.status_code == 404
