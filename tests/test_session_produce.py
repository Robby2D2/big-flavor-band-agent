"""Grouping a session's takes into songs, and producing a group into the catalog.

Against a fake DatabaseManager and a tmp audio library — no live DB, no audio
decode. The contracts:

  - moving a take between songs, out on its own, or into a new song (SESS-18),
    and a take that already became a catalog version leaving that song as it
    moves, staged to be produced into its new one,
  - producing a group makes one **new** song in the session id range whose
    versions are the group's kept takes, with **no default** (SESS-15, SESS-19),
  - producing again returns the same song and adds only takes that joined since,
  - the catalog keeps its own copy of the audio, and the takes' channels become
    each version's stem set under the band's own track names (SESS-11),
  - re-guessing the songs leaves a produced group and its takes alone,
  - a session song's versions list works with no catalog original on disk.
"""
import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api
from database import SESSION_SONG_ID_START
from src.api import radio_service, session_jobs
from src.api.dependencies import get_db
from src.api.routers import produce

_SECRET = "test-secret-value"


def _editor_headers(monkeypatch):
    monkeypatch.setenv("BACKEND_API_SECRET", _SECRET)
    return {"X-Service-Secret": _SECRET, "X-User-Role": "editor"}


class FakeDB:
    """The session, song, version and stem-set persistence the routes use."""

    def __init__(self):
        self.sessions = {}
        self.takes = {}
        self.groups = {}
        self.songs = {}
        self.versions = {}
        self.stem_sets = {}
        self.stems = {}
        self._ids = iter(range(1, 10_000))
        self._next_song = SESSION_SONG_ID_START

    def _id(self):
        return next(self._ids)

    # --- seeding -----------------------------------------------------------
    def add_session(self, status="complete"):
        sid = self._id()
        self.sessions[sid] = {
            "id": sid, "name": "Super Remodel", "status": status,
            "recorded_on": datetime.date(2024, 6, 21),
        }
        return sid

    def add_group(self, session_id, name=None):
        gid = self._id()
        self.groups[gid] = {
            "id": gid, "session_id": session_id, "name": name, "song_id": None,
        }
        return gid

    def add_take(self, session_id, group_id, start, mix_path, stems=(), excluded=False):
        tid = self._id()
        self.takes[tid] = {
            "id": tid, "session_id": session_id, "group_id": group_id,
            "rec_pass": 1, "start_seconds": start, "end_seconds": start + 239,
            "transcript": "only coming through in waves", "mix_path": mix_path,
            "excluded": excluded, "song_version_id": None,
            "stems": [
                {"id": self._id(), "name": name, "display_name": display, "path": path}
                for name, display, path in stems
            ],
        }
        return tid

    # --- sessions ----------------------------------------------------------
    async def get_recording_session(self, session_id):
        return self.sessions.get(session_id)

    async def list_session_takes(self, session_id):
        rows = [t for t in self.takes.values() if t["session_id"] == session_id]
        return sorted(rows, key=lambda t: t["start_seconds"])

    async def get_session_take(self, take_id):
        take = self.takes.get(take_id)
        return {k: v for k, v in take.items() if k != "stems"} if take else None

    async def set_session_take_excluded(self, take_id, excluded):
        self.takes[take_id]["excluded"] = excluded
        return await self.get_session_take(take_id)

    async def set_session_take_group_id(self, take_id, group_id):
        previous = self.takes[take_id]["group_id"]
        self.takes[take_id]["group_id"] = group_id
        if previous is not None and previous != group_id:
            group = self.groups.get(previous)
            if group and group["song_id"] is None and not any(
                t["group_id"] == previous for t in self.takes.values()
            ):
                del self.groups[previous]
        return await self.get_session_take(take_id)

    async def create_session_take_group(self, session_id):
        return self.groups[self.add_group(session_id)]

    async def list_session_take_groups(self, session_id):
        return [g for g in self.groups.values() if g["session_id"] == session_id]

    async def get_session_take_group(self, group_id):
        return self.groups.get(group_id)

    async def set_session_take_group_name(self, group_id, name):
        self.groups[group_id]["name"] = name
        return self.groups[group_id]

    async def clear_session_take_groups(self, session_id):
        for gid in [
            g["id"] for g in self.groups.values()
            if g["session_id"] == session_id and g["song_id"] is None
        ]:
            del self.groups[gid]
            for take in self.takes.values():
                if take["group_id"] == gid:
                    take["group_id"] = None

    async def ensure_session_group_song(self, group_id, title, recorded_on):
        group = self.groups[group_id]
        if group["song_id"] is None:
            song_id = self._next_song
            self._next_song += 1
            self.songs[song_id] = {"id": song_id, "title": title, "recorded_on": recorded_on}
            group["song_id"] = song_id
        return group["song_id"]

    async def release_session_take_version(self, take_id):
        version_id = self.takes[take_id]["song_version_id"]
        if version_id is None:
            return None
        stem_sets = [
            self.stem_sets.pop(sid) for sid in [
                s["id"] for s in self.stem_sets.values()
                if s["source_version_id"] == version_id
            ]
        ]
        self.takes[take_id]["song_version_id"] = None
        return {"version": self.versions.pop(version_id, None), "stem_sets": stem_sets}

    async def set_session_take_song_version(self, take_id, version_id):
        self.takes[take_id]["song_version_id"] = version_id
        return await self.get_session_take(take_id)

    # --- versions ----------------------------------------------------------
    async def add_song_version(self, song_id, audio_path, label="cleaned", metrics=None):
        for version in self.versions.values():
            if version["audio_path"] == audio_path:
                return version
        vid = self._id()
        self.versions[vid] = {
            "id": vid, "song_id": song_id, "audio_path": audio_path, "label": label,
            "name": None, "is_published": False, "metrics": metrics,
            "created_at": datetime.datetime(2026, 1, 1) + datetime.timedelta(minutes=vid),
        }
        return self.versions[vid]

    async def rename_song_version(self, version_id, name):
        self.versions[version_id]["name"] = name
        return self.versions[version_id]

    async def list_song_versions(self, song_id):
        rows = [v for v in self.versions.values() if v["song_id"] == song_id]
        return sorted(rows, key=lambda v: v["created_at"], reverse=True)

    async def ensure_original_version(self, song_id, audio_path):
        raise AssertionError("a session song has no catalog original to seed")

    async def get_song_version(self, version_id):
        return self.versions.get(version_id)

    async def get_published_version(self, song_id):
        return next(
            (v for v in self.versions.values() if v["song_id"] == song_id and v["is_published"]),
            None,
        )

    # --- stems -------------------------------------------------------------
    async def create_stem_set(self, song_id, model, source_version_id=None):
        sid = self._id()
        self.stem_sets[sid] = {
            "id": sid, "song_id": song_id, "model": model,
            "source_version_id": source_version_id, "status": "queued", "origin": None,
        }
        return self.stem_sets[sid]

    async def add_stem(self, stem_set_id, name, path):
        sid = self._id()
        self.stems[sid] = {
            "id": sid, "stem_set_id": stem_set_id, "name": name, "path": path,
            "display_name": None,
        }
        return self.stems[sid]

    async def set_stem_display_name(self, stem_id, display_name):
        self.stems[stem_id]["display_name"] = display_name
        return self.stems[stem_id]

    async def set_stem_set_origin(self, stem_set_id, origin):
        self.stem_sets[stem_set_id]["origin"] = origin

    async def set_stem_set_status(self, stem_set_id, status, error=None):
        self.stem_sets[stem_set_id]["status"] = status
        return self.stem_sets[stem_set_id]


@pytest.fixture
def session_client(tmp_path, monkeypatch):
    audio_library = tmp_path / "audio_library"
    audio_library.mkdir()
    monkeypatch.setattr(radio_service, "AUDIO_LIBRARY_DIR", audio_library)
    # Instrument tagging is a background DSP job with nothing to say here.
    monkeypatch.setattr(produce, "_tag_in_background", lambda rows, db: None)
    # Playback copies are ffmpeg work behind the response, likewise.
    monkeypatch.setattr(produce, "_warm_previews_in_background", lambda rows: None)
    monkeypatch.setattr(produce, "warm_version_preview_in_background", lambda path: None)

    db = FakeDB()
    backend_api.app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(backend_api.app), db, tmp_path
    finally:
        backend_api.app.dependency_overrides.clear()


def _rendered_take(tmp_path, name):
    """A take's mix and two channels, where a scan would have rendered them."""
    folder = tmp_path / "sessions" / name
    (folder / "stems").mkdir(parents=True)
    mix = folder / "mix.wav"
    mix.write_bytes(b"mix-" + name.encode())
    vox = folder / "stems" / "vocals.flac"
    vox.write_bytes(b"vox")
    bass = folder / "stems" / "bass.flac"
    bass.write_bytes(b"bass")
    return str(mix), [
        ("vocals", "4 Kev Vox", str(vox)),
        ("bass", "5 Tom Instr (bass too high)", str(bass)),
    ]


def _seed_song(db, tmp_path):
    session = db.add_session()
    group = db.add_group(session)
    mix1, stems1 = _rendered_take(tmp_path, "t1")
    mix2, stems2 = _rendered_take(tmp_path, "t2")
    mix3, _ = _rendered_take(tmp_path, "t3")
    first = db.add_take(session, group, 10.0, mix1, stems1)
    second = db.add_take(session, group, 400.0, mix2, stems2)
    discarded = db.add_take(session, group, 800.0, mix3, excluded=True)
    return session, group, (first, second, discarded)


def _produce(client, monkeypatch, group, title="only coming through in waves your"):
    return client.post(
        f"/api/produce/sessions/groups/{group}/produce",
        json={"title": title},
        headers=_editor_headers(monkeypatch),
    )


def test_producing_a_group_makes_a_new_song_with_no_default(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, (first, second, discarded) = _seed_song(db, tmp_path)

    resp = _produce(client, monkeypatch, group)

    assert resp.status_code == 200
    song_id = resp.json()["song_id"]
    assert song_id >= SESSION_SONG_ID_START
    assert db.songs[song_id]["title"] == "only coming through in waves your"
    assert db.groups[group]["song_id"] == song_id

    versions = sorted(db.versions.values(), key=lambda v: v["id"])
    assert [v["name"] for v in versions] == ["Take 1 (3:59)", "Take 2 (3:59)"]
    assert all(v["label"] == "session" for v in versions)
    # The producer chooses the default on the produce page, never the import.
    assert not any(v["is_published"] for v in versions)
    # A discarded take stays behind.
    assert db.takes[discarded]["song_version_id"] is None
    assert db.takes[first]["song_version_id"] == versions[0]["id"]


def test_catalog_keeps_its_own_copy_of_the_audio(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, (first, *_) = _seed_song(db, tmp_path)

    song_id = _produce(client, monkeypatch, group).json()["song_id"]

    version = db.versions[db.takes[first]["song_version_id"]]
    copy = Path(version["audio_path"])
    assert copy.read_bytes() == b"mix-t1"
    assert copy.parent == (
        radio_service.AUDIO_LIBRARY_DIR / "produced" / str(song_id) / "session"
    )
    # Deleting the session removes its folder; the catalog must not notice.
    assert Path(db.takes[first]["mix_path"]).parent not in copy.parents


def test_take_channels_become_the_versions_stem_set(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, (first, *_) = _seed_song(db, tmp_path)

    _produce(client, monkeypatch, group)

    version_id = db.takes[first]["song_version_id"]
    (stem_set,) = [s for s in db.stem_sets.values() if s["source_version_id"] == version_id]
    assert stem_set["status"] == "complete"
    assert stem_set["origin"] == "session"
    stems = {s["name"]: s for s in db.stems.values() if s["stem_set_id"] == stem_set["id"]}
    assert stems["vocals"]["display_name"] == "4 Kev Vox"
    assert Path(stems["bass"]["path"]).read_bytes() == b"bass"


def test_producing_again_adds_only_new_takes(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session, group, _ = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]

    again = _produce(client, monkeypatch, group)
    assert again.json() == {"song_id": song_id, "added_versions": []}
    assert len(db.versions) == 2

    mix, stems = _rendered_take(tmp_path, "t4")
    late = db.add_take(session, None, 1200.0, mix, stems)
    moved = client.patch(
        f"/api/produce/sessions/takes/{late}",
        json={"group_id": group},
        headers=_editor_headers(monkeypatch),
    )
    assert moved.status_code == 200

    third = _produce(client, monkeypatch, group).json()
    assert third["song_id"] == song_id
    assert third["added_versions"] == [db.takes[late]["song_version_id"]]
    assert len(db.songs) == 1


def test_a_hand_set_name_wins_over_the_pages_guess(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, _ = _seed_song(db, tmp_path)
    db.groups[group]["name"] = "Waves"

    song_id = _produce(client, monkeypatch, group, title="only coming through").json()["song_id"]

    assert db.songs[song_id]["title"] == "Waves"


def test_cannot_produce_while_scanning(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session, group, _ = _seed_song(db, tmp_path)
    db.sessions[session]["status"] = "running"

    assert _produce(client, monkeypatch, group).status_code == 409
    assert db.songs == {}


def test_a_group_of_only_discarded_takes_cannot_be_produced(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session = db.add_session()
    group = db.add_group(session)
    mix, _ = _rendered_take(tmp_path, "t1")
    db.add_take(session, group, 10.0, mix, excluded=True)

    assert _produce(client, monkeypatch, group).status_code == 409
    assert db.songs == {}


def test_a_lone_take_becomes_a_song_of_its_own(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session = db.add_session()
    mix, _ = _rendered_take(tmp_path, "t1")
    lone = db.add_take(session, None, 10.0, mix)

    resp = client.post(
        f"/api/produce/sessions/{session}/groups",
        json={"take_ids": [lone]},
        headers=_editor_headers(monkeypatch),
    )

    assert resp.status_code == 200
    assert db.takes[lone]["group_id"] == resp.json()["id"]
    assert resp.json()["song_id"] is None


def test_moving_a_take_out_drops_the_guess_it_leaves_empty(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session = db.add_session()
    group = db.add_group(session)
    mix, _ = _rendered_take(tmp_path, "t1")
    take = db.add_take(session, group, 10.0, mix)

    resp = client.patch(
        f"/api/produce/sessions/takes/{take}",
        json={"group_id": None},
        headers=_editor_headers(monkeypatch),
    )

    assert resp.status_code == 200
    assert db.takes[take]["group_id"] is None
    assert group not in db.groups


def test_a_take_cannot_move_to_another_sessions_song(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session = db.add_session()
    elsewhere = db.add_group(db.add_session())
    mix, _ = _rendered_take(tmp_path, "t1")
    take = db.add_take(session, None, 10.0, mix)

    resp = client.patch(
        f"/api/produce/sessions/takes/{take}",
        json={"group_id": elsewhere},
        headers=_editor_headers(monkeypatch),
    )

    assert resp.status_code == 400
    assert db.takes[take]["group_id"] is None


def test_a_produced_take_moves_out_of_its_catalog_song(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, (first, second, _) = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]
    version = db.versions[db.takes[first]["song_version_id"]]
    stem_set = next(
        s for s in db.stem_sets.values() if s["source_version_id"] == version["id"]
    )
    stem_dir = produce._stem_set_output_dir(song_id, stem_set["id"])
    assert stem_dir.exists()

    resp = client.patch(
        f"/api/produce/sessions/takes/{first}",
        json={"group_id": None},
        headers=_editor_headers(monkeypatch),
    )

    assert resp.status_code == 200
    assert db.takes[first]["group_id"] is None
    assert db.takes[first]["song_version_id"] is None
    # Its version, copied audio and channels leave the song it went to...
    assert version["id"] not in db.versions
    assert not Path(version["audio_path"]).exists()
    assert stem_set["id"] not in db.stem_sets
    assert not stem_dir.exists()
    # ...its sibling stays, and the take's own session audio is untouched.
    assert db.takes[second]["song_version_id"] in db.versions
    assert Path(db.takes[first]["mix_path"]).exists()


def test_a_moved_produced_take_joins_its_new_song_when_produced(
    session_client, monkeypatch
):
    client, db, tmp_path = session_client
    session, group, (first, *_) = _seed_song(db, tmp_path)
    old_song = _produce(client, monkeypatch, group).json()["song_id"]

    resp = client.post(
        f"/api/produce/sessions/{session}/groups",
        json={"take_ids": [first]},
        headers=_editor_headers(monkeypatch),
    )
    assert resp.status_code == 200
    new_group = resp.json()["id"]

    new_song = _produce(client, monkeypatch, new_group, title="another song").json()[
        "song_id"
    ]

    assert new_song != old_song
    version = db.versions[db.takes[first]["song_version_id"]]
    assert version["song_id"] == new_song
    assert [v["song_id"] for v in db.versions.values()].count(old_song) == 1


def test_moving_a_produced_default_leaves_its_song_with_none(
    session_client, monkeypatch
):
    client, db, tmp_path = session_client
    _, group, (first, *_) = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]
    version = db.versions[db.takes[first]["song_version_id"]]
    version["is_published"] = True
    radio_service.set_published_version_path(song_id, version["audio_path"])

    client.patch(
        f"/api/produce/sessions/takes/{first}",
        json={"group_id": None},
        headers=_editor_headers(monkeypatch),
    )

    # The product never picks a replacement default (SESS-15).
    assert not any(
        v["is_published"] for v in db.versions.values() if v["song_id"] == song_id
    )
    assert song_id not in radio_service._published_version_paths


def test_discarding_still_works_alone(session_client, monkeypatch):
    client, db, tmp_path = session_client
    _, group, (first, *_) = _seed_song(db, tmp_path)

    resp = client.patch(
        f"/api/produce/sessions/takes/{first}",
        json={"excluded": True},
        headers=_editor_headers(monkeypatch),
    )

    assert resp.status_code == 200
    assert db.takes[first]["excluded"] is True
    assert db.takes[first]["group_id"] == group


@pytest.mark.asyncio
async def test_reguessing_leaves_a_produced_song_alone(session_client, monkeypatch):
    client, db, tmp_path = session_client
    session, group, (first, second, discarded) = _seed_song(db, tmp_path)
    _produce(client, monkeypatch, group)
    staged = db.add_group(session)
    mix, _ = _rendered_take(tmp_path, "t9")
    loose = db.add_take(session, staged, 2000.0, mix)

    seen = []

    def spy(takes):
        seen.extend(t["id"] for t in takes)
        return []

    monkeypatch.setattr(session_jobs.session_grouping, "group_takes", spy)
    await session_jobs.group_session_takes(db, session)

    assert db.groups[group]["song_id"] is not None
    assert db.takes[first]["group_id"] == group
    assert db.takes[discarded]["group_id"] == group
    # Only takes outside a produced song are guessed again.
    assert seen == [loose]
    assert staged not in db.groups


def test_a_session_songs_versions_list_needs_no_catalog_original(
    session_client, monkeypatch
):
    client, db, tmp_path = session_client
    _, group, _ = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]

    resp = client.get(
        f"/api/produce/songs/{song_id}/versions", headers=_editor_headers(monkeypatch)
    )

    assert resp.status_code == 200
    assert len(resp.json()["versions"]) == 2


# --- a session song has no catalog file (saving and lyrics used to 404) ------

@pytest.mark.asyncio
async def test_saving_a_fixed_mix_of_a_session_song_needs_no_catalog_file(
    session_client, monkeypatch
):
    """"Accept all & save" 404'd with "Audio file for song 1000000 not found":
    saving seeded an 'original' version from a catalog MP3 the song never had."""
    client, db, tmp_path = session_client
    _, group, _ = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]

    saved = await produce.save_candidate_version(song_id, "/produced/mix.wav", {}, db)

    assert db.versions[saved["version_id"]]["label"] == "cleaned"
    assert saved["is_published"] is False


@pytest.mark.asyncio
async def test_a_session_songs_own_audio_is_its_default_then_its_newest_take(
    session_client, monkeypatch
):
    """What lyric extraction (and any whole-song tool) reads when no version is
    named: the catalog file for a catalog song; for a session song, which has
    none, the default version — or before one is chosen, the newest take."""
    client, db, tmp_path = session_client
    _, group, (first, second, _) = _seed_song(db, tmp_path)
    song_id = _produce(client, monkeypatch, group).json()["song_id"]
    take1 = db.versions[db.takes[first]["song_version_id"]]
    take2 = db.versions[db.takes[second]["song_version_id"]]

    newest = await produce._resolve_clean_source_path(song_id, None, db)
    assert str(newest) == take2["audio_path"]

    take1["is_published"] = True
    default = await produce._resolve_clean_source_path(song_id, None, db)
    assert str(default) == take1["audio_path"]
