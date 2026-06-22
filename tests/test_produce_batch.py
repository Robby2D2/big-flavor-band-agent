"""Tests for the catalog-wide auto-clean batch runner (issue #29).

Drive the BatchCleanManager directly with fake agent/db/rag (no live DB, LLM, or
real audio). The manager reuses the single-track produce helpers, so the source
path resolve and librosa measurement are stubbed. These assert the batch's
contract:
  - "not_cleaned" selection skips songs that already have a cleaned version and
    reports them skipped (no reprocessing),
  - "force_reclean_all" reprocesses every selected song regardless of state,
  - one track's auto-clean failure is recorded as failed and the batch continues
    with the rest (and never overwrites originals — output is a new version),
  - the per-track summary counts (succeeded / skipped / failed) are correct,
  - a second batch can't start while one is running.
"""
import asyncio
import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api import produce_batch
from src.api.routers import produce


class FakeAgent:
    """Returns a success cleanup payload, or a failure for song ids in fail_ids."""

    def __init__(self, fail_ids=None):
        self.fail_ids = set(fail_ids or [])
        self.cleaned_song_ids = []

    async def execute_tool(self, tool_name, parameters):
        # Derive the song id from the output path "{produced}/{song_id}_cleaned_*.wav".
        song_id = int(Path(parameters["output_path"]).name.split("_", 1)[0])
        self.cleaned_song_ids.append(song_id)
        if song_id in self.fail_ids:
            return {"status": "error", "error": "decode failed"}
        Path(parameters["output_path"]).write_bytes(b"cleaned-audio")
        return {"status": "success", "aggressiveness": parameters.get("aggressiveness"),
                "steps_applied": []}


class FakeRag:
    def __init__(self):
        self.indexed = []

    async def index_audio_file(self, audio_path, song_id):
        self.indexed.append((audio_path, song_id))
        return True


class FakeDB:
    def __init__(self, songs, cleaned_ids):
        self._songs = songs
        self._cleaned_ids = set(cleaned_ids)
        self.published = []

    async def get_all_songs(self):
        return list(self._songs)

    async def get_song_ids_with_cleaned_versions(self):
        return set(self._cleaned_ids)

    async def ensure_original_version(self, song_id, audio_path):
        return {"id": 0, "song_id": song_id, "label": "original"}

    async def add_song_version(self, song_id, audio_path, label="cleaned", metrics=None):
        return {"id": song_id * 10, "song_id": song_id, "label": label}

    async def publish_song_version(self, song_id, version_id):
        self.published.append(song_id)
        self._cleaned_ids.add(song_id)
        return {"id": version_id, "song_id": song_id, "is_published": True}


@pytest.fixture
def patched(tmp_path, monkeypatch):
    """Point produce at a temp audio library and stub librosa measurement."""
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    from src.api import radio_service

    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    radio_service.set_published_version_paths({})
    # Every song has a resolvable source file.
    for sid in (1, 2, 3):
        (audio_library / f"{sid}_track.mp3").write_bytes(b"original")
    # Avoid librosa; produce helpers call _measure_audio on source + candidate.
    monkeypatch.setattr(produce, "_measure_audio", lambda path: {"peak_db": -1.0})
    # Use a fresh manager per test so process-wide state doesn't leak.
    monkeypatch.setattr(produce_batch, "manager", produce_batch.BatchCleanManager())
    return audio_library


async def _run_batch(selection, force, agent, db, rag):
    mgr = produce_batch.manager
    mgr.start(selection, "moderate", force, agent, db, rag)
    # Drive the background task to completion.
    while mgr.is_running():
        await asyncio.sleep(0)
    return mgr.status()


SONGS = [
    {"id": 1, "title": "One"},
    {"id": 2, "title": "Two"},
    {"id": 3, "title": "Three"},
]


@pytest.mark.asyncio
async def test_not_cleaned_skips_already_cleaned(patched):
    agent, rag = FakeAgent(), FakeRag()
    db = FakeDB(SONGS, cleaned_ids={2})  # song 2 already cleaned

    status = await _run_batch("not_cleaned", False, agent, db, rag)

    assert status["status"] == "completed"
    # not_cleaned excludes already-cleaned song 2 from the target set entirely.
    assert status["total"] == 2
    assert sorted(agent.cleaned_song_ids) == [1, 3]
    assert status["succeeded"] == 2
    assert status["failed"] == 0
    assert db.published == [1, 3]


@pytest.mark.asyncio
async def test_force_reclean_all_reprocesses_every_song(patched):
    agent, rag = FakeAgent(), FakeRag()
    db = FakeDB(SONGS, cleaned_ids={2})

    status = await _run_batch("all", True, agent, db, rag)

    assert status["status"] == "completed"
    assert status["total"] == 3
    # Force reclean ignores existing cleaned state — every song reprocessed.
    assert sorted(agent.cleaned_song_ids) == [1, 2, 3]
    assert status["succeeded"] == 3
    assert status["skipped"] == 0


@pytest.mark.asyncio
async def test_all_selection_skips_cleaned_without_force(patched):
    agent, rag = FakeAgent(), FakeRag()
    db = FakeDB(SONGS, cleaned_ids={2})

    status = await _run_batch("all", False, agent, db, rag)

    # "all" targets every song, but the default still skips already-cleaned ones.
    assert status["total"] == 3
    assert status["skipped"] == 1
    assert status["succeeded"] == 2
    skipped = [r for r in status["results"] if r["outcome"] == "skipped"]
    assert skipped[0]["song_id"] == 2
    assert skipped[0]["reason"] == "already cleaned"


@pytest.mark.asyncio
async def test_one_failure_is_recorded_and_batch_continues(patched):
    agent = FakeAgent(fail_ids={2})  # song 2's clean fails
    rag = FakeRag()
    db = FakeDB(SONGS, cleaned_ids=set())

    status = await _run_batch("all", False, agent, db, rag)

    assert status["status"] == "completed"
    assert status["total"] == 3
    assert status["succeeded"] == 2
    assert status["failed"] == 1
    # The other two still published — one failure does not abort the batch.
    assert sorted(db.published) == [1, 3]
    failed = [r for r in status["results"] if r["outcome"] == "failed"]
    assert failed[0]["song_id"] == 2
    assert failed[0]["reason"]


@pytest.mark.asyncio
async def test_cannot_start_second_batch_while_running(patched):
    agent, rag = FakeAgent(), FakeRag()
    db = FakeDB(SONGS, cleaned_ids=set())
    mgr = produce_batch.manager

    mgr.start("all", "moderate", False, agent, db, rag)
    with pytest.raises(RuntimeError):
        mgr.start("all", "moderate", False, agent, db, rag)

    while mgr.is_running():
        await asyncio.sleep(0)
    assert mgr.status()["status"] == "completed"
