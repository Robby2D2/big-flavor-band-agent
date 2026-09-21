"""``_keep_rendered_stems`` — the stems a save rendered become that version's set.

The fix queue already produces per-stem audio for the exact mix it saves, so the
new version's parts exist the moment it is saved. Keeping them is what stops a
producer selecting the version they just made and being told to wait minutes for
Demucs — on a mix that was itself assembled from stems.
"""

from pathlib import Path

import pytest

from src.api.routers import produce


class FakeDB:
    """In-memory stand-in for the stem-set writes the helper makes."""

    def __init__(self):
        self.stem_sets = {}
        self.stems = {}
        self.origins = {}
        self._next_set = 100
        self._next_stem = 500

    async def create_stem_set(self, song_id, model, source_version_id=None):
        set_id = self._next_set
        self._next_set += 1
        row = {
            "id": set_id,
            "song_id": song_id,
            "model": model,
            "source_version_id": source_version_id,
            "status": "queued",
            "error": None,
            "created_at": None,
        }
        self.stem_sets[set_id] = row
        return row

    async def add_stem(self, stem_set_id, name, path):
        stem_id = self._next_stem
        self._next_stem += 1
        row = {"id": stem_id, "stem_set_id": stem_set_id, "name": name, "path": path}
        self.stems[stem_id] = row
        return row

    async def set_stem_set_status(self, stem_set_id, status, error=None):
        self.stem_sets[stem_set_id]["status"] = status
        self.stem_sets[stem_set_id]["error"] = error
        return self.stem_sets[stem_set_id]

    async def set_stem_set_origin(self, stem_set_id, origin):
        self.origins[stem_set_id] = origin
        self.stem_sets[stem_set_id]["origin"] = origin

    async def set_stem_instrument_tags(self, stem_id, tags):
        pass


@pytest.fixture
def produced_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(produce, "_produced_dir", lambda: tmp_path)
    return tmp_path


def _part(tmp_path: Path, name: str, body: bytes) -> dict:
    path = tmp_path / f"{name}_source.wav"
    path.write_bytes(body)
    return {"name": name, "path": str(path)}


@pytest.mark.asyncio
async def test_every_part_is_copied_not_referenced(produced_dir, tmp_path):
    """Including the ones no fix touched.

    An untouched stem arrives pointing at the *previous* set's file, and two sets
    sharing one path is a trap: re-separating or cleaning up the older set would
    hollow this one out.
    """
    db = FakeDB()
    parts = [_part(tmp_path, "vocals", b"fixed"), _part(tmp_path, "bass", b"untouched")]

    stem_set = await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=parts, had_master_fixes=False, model="htdemucs_6s", db=db
    )

    assert stem_set is not None
    kept = sorted(db.stems.values(), key=lambda r: r["name"])
    assert [r["name"] for r in kept] == ["bass", "vocals"]
    for row in kept:
        copied = Path(row["path"])
        assert copied.exists()
        # A copy inside the set's own directory, not the source it came from.
        assert str(produced_dir) in str(copied)
        assert copied != Path(dict((p["name"], p["path"]) for p in parts)[row["name"]])
    # The originals survive — copying must not move them.
    assert all(Path(p["path"]).exists() for p in parts)


@pytest.mark.asyncio
async def test_set_is_attributed_to_the_new_version_and_marked_complete(produced_dir, tmp_path):
    db = FakeDB()
    parts = [_part(tmp_path, "vocals", b"a")]

    stem_set = await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=parts, had_master_fixes=False, model="htdemucs_6s", db=db
    )

    assert stem_set["source_version_id"] == 42
    assert stem_set["status"] == "complete"
    # Names the separator the audio ultimately came from.
    assert stem_set["model"] == "htdemucs_6s"


@pytest.mark.asyncio
async def test_master_fixes_mark_the_set_premaster(produced_dir, tmp_path):
    """Master fixes run after the remix, so the parts sum to the pre-master mix."""
    db = FakeDB()
    parts = [_part(tmp_path, "vocals", b"a")]

    await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=parts, had_master_fixes=True, model=None, db=db
    )
    assert list(db.origins.values()) == ["fixes_premaster"]

    db2 = FakeDB()
    await produce._keep_rendered_stems(
        song_id=7, version_id=43, parts=[_part(tmp_path, "drums", b"b")],
        had_master_fixes=False, model=None, db=db2,
    )
    assert list(db2.origins.values()) == ["fixes"]


@pytest.mark.asyncio
async def test_no_parts_keeps_nothing(produced_dir):
    """A master-only run mixed no stems, so there is no set to keep."""
    db = FakeDB()
    assert await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=[], had_master_fixes=True, model=None, db=db
    ) is None
    assert db.stem_sets == {}


@pytest.mark.asyncio
async def test_a_missing_part_file_does_not_sink_the_save(produced_dir, tmp_path):
    """The version is already saved; keeping stems is a bonus that fails quietly."""
    db = FakeDB()
    parts = [
        _part(tmp_path, "vocals", b"a"),
        {"name": "ghost", "path": str(tmp_path / "does_not_exist.wav")},
    ]

    stem_set = await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=parts, had_master_fixes=False, model=None, db=db
    )

    # The real part is kept; the missing one is skipped rather than raising.
    assert stem_set is not None
    assert [r["name"] for r in db.stems.values()] == ["vocals"]


@pytest.mark.asyncio
async def test_all_parts_missing_marks_the_set_failed(produced_dir, tmp_path):
    db = FakeDB()
    parts = [{"name": "ghost", "path": str(tmp_path / "nope.wav")}]

    assert await produce._keep_rendered_stems(
        song_id=7, version_id=42, parts=parts, had_master_fixes=False, model=None, db=db
    ) is None
    assert [r["status"] for r in db.stem_sets.values()] == ["failed"]


# ---- the invariant the feature was asked for: previews keep nothing ---------


@pytest.mark.asyncio
async def test_a_preview_never_registers_a_stem_set(produced_dir, tmp_path, monkeypatch):
    """Guarded at two independent call sites, so worth pinning at the seam both share.

    A preview is an audition. Registering its parts would attach stems to a
    version that was never saved — and every warm-up render the queue fires is a
    preview.
    """
    kept = []

    async def spy(*args, **kwargs):
        kept.append(kwargs or args)
        return None

    monkeypatch.setattr(produce, "_keep_rendered_stems", spy)

    async def fake_render(request, agent, db):
        return Path(tmp_path / "mix.wav"), [], [{"name": "vocals", "path": "x"}], "htdemucs_6s"

    monkeypatch.setattr(produce, "_render_mix", fake_render)
    monkeypatch.setattr(produce.accept_jobs, "remember_render", lambda *a, **k: None)

    class Req:
        song_id = 7
        source_version_id = 3
        stems = []
        master_fixes = []
        preview = True

    monkeypatch.setattr(produce, "_accept_fingerprint", lambda r: "print")
    result = await produce._render_accept_fixes(Req(), agent=None, db=None)

    assert "candidate_path" in result
    assert kept == [], "a preview must not keep stems"
