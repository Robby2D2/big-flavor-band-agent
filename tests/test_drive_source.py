"""Tests for the Google Drive session source (src/production/drive_source.py).

Drive is replaced by a fake ``requests`` session that answers from a dict, so
these run offline and pin down the parts that matter when real gigabytes are on
the line: a dropped download resumes rather than restarting or corrupting, a
short download is never passed off as whole, and only the files the project
references are fetched.
"""
import json
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production import drive_source  # noqa: E402
from src.production.drive_source import (  # noqa: E402
    FOLDER_MIME,
    DriveClient,
    DriveError,
    DriveFile,
    SessionFile,
    media_to_fetch,
    project_candidates,
)

ROOT = "rootFolder0001"


class FakeResponse:
    def __init__(self, status=200, body=None, content=b"", drop_after=None):
        self.status_code = status
        self._body = body
        self._content = content
        self._drop_after = drop_after

    @property
    def ok(self):
        return self.status_code < 400

    @property
    def text(self):
        return json.dumps(self._body) if self._body is not None else ""

    reason = "fake"

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body

    def iter_content(self, _chunk):
        if self._drop_after is None:
            yield self._content
            return
        yield self._content[: self._drop_after]
        raise requests.ConnectionError("connection reset")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeSession:
    """Answers queued responses per URL and records every request made."""

    def __init__(self, responses):
        self._responses = {url: list(queue) for url, queue in responses.items()}
        self.calls = []

    def get(self, url, params=None, headers=None, **_kwargs):
        self.calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        return self._responses[url].pop(0)


def folder(id_, name):
    return {"id": id_, "name": name, "mimeType": FOLDER_MIME}


def file(id_, name, size):
    return {"id": id_, "name": name, "mimeType": "audio/x-wavpack", "size": str(size)}


# --- listing ----------------------------------------------------------------

def test_list_children_follows_pages():
    session = FakeSession({drive_source.DRIVE_FILES_URL: [
        FakeResponse(body={"files": [file("f1", "a.wv", 1)], "nextPageToken": "p2"}),
        FakeResponse(body={"files": [file("f2", "b.wv", 2)]}),
    ]})

    names = [item.name for item in DriveClient(session).list_children(ROOT)]

    assert names == ["a.wv", "b.wv"]
    assert session.calls[1]["params"]["pageToken"] == "p2"


def test_list_children_rejects_a_non_id_before_querying():
    session = FakeSession({})
    with pytest.raises(DriveError):
        DriveClient(session).list_children("x' or name contains '")
    assert session.calls == []


def test_drive_error_carries_googles_message():
    """"API not enabled" is the fix the owner needs to see, so it is passed on."""
    message = "Google Drive API has not been used in project 123 before or it is disabled."
    session = FakeSession({drive_source.DRIVE_FILES_URL: [
        FakeResponse(status=403, body={"error": {"code": 403, "message": message}}),
    ]})

    with pytest.raises(DriveError, match="has not been used in project 123"):
        DriveClient(session).list_children(ROOT)


class FakeTree:
    """A Drive folder tree: each listing is answered from ``children[parent]``."""

    def __init__(self, children):
        self.children = children
        self.listed = []

    def get(self, url, params=None, **_kwargs):
        parent = params["q"].split("'")[1]
        self.listed.append(parent)
        return FakeResponse(body={"files": self.children.get(parent, [])})


def wv(name, size=100):
    return file(f"id-{name}".replace(" ", "-").replace(".", "-"), name, size)


def rpp(name):
    return file(f"id-{name}".replace(" ", "-").replace(".", "-"), name, 5)


#: The shapes the band's real Drive has, trimmed: a night filed at the top
#: level, a night with an "Audio/" sub-folder, a night with later nights filed
#: *inside* it, a folder that is only media, and an "_Archive" that is not
#: searched at all.
TREE = {
    ROOT: [
        folder("topNight0001", "20260501 May the Farts Be With You"),
        folder("julyChrist01", "20240719 - July Christie"),
        folder("mediaOnly001", "20250124 - Waitlisted"),
        folder("archive00001", "_Archive"),
    ],
    "topNight0001": [rpp("1. Warm Up.RPP"), wv("01-Kev Vox.wv"), folder("audioSub0001", "Audio")],
    "audioSub0001": [wv("02-Drums.wv")],
    "julyChrist01": [
        rpp("1. Warm Up.RPP"), rpp("1. Warm Up.RPP-bak"), wv("01-July.wv"),
        folder("nestedNight1", "20250213 - Broken Tooth"),
    ],
    "nestedNight1": [rpp("1. Warm Up.RPP"), rpp("2. Warm Up.RPP"), wv("01-Tooth.wv")],
    "mediaOnly001": [wv("01-Wait.wv")],
    "archive00001": [rpp("Old.RPP")],
}


def test_find_sessions_finds_every_folder_holding_a_project_at_any_depth():
    tree = FakeTree(TREE)

    found = drive_source.find_sessions(DriveClient(tree), ROOT)

    assert [(s.folder.name, s.location) for s in found] == [
        ("20260501 May the Farts Be With You", ()),
        ("20250213 - Broken Tooth", ("20240719 - July Christie",)),
        ("20240719 - July Christie", ()),
    ]
    assert "archive00001" not in tree.listed


def test_session_files_keep_media_subfolders_but_not_nested_nights():
    top = drive_source.session_files(DriveClient(FakeTree(TREE)), "topNight0001")
    july = drive_source.session_files(DriveClient(FakeTree(TREE)), "julyChrist01")

    assert sorted((e.file.name, e.depth) for e in top) == [
        ("01-Kev Vox.wv", 0), ("02-Drums.wv", 1), ("1. Warm Up.RPP", 0),
    ]
    assert "01-Tooth.wv" not in {e.file.name for e in july}


# --- choosing what to fetch -------------------------------------------------

def _files(*entries):
    """(name, size) or (name, size, depth) -> SessionFile list."""
    out = []
    for i, entry in enumerate(entries):
        name, size, depth = (entry + (0,))[:3]
        out.append(SessionFile(DriveFile(id=f"id{i}", name=name, mime_type="x", size=size), depth))
    return out


def test_project_candidates_are_the_folders_own_projects_not_backups():
    files = _files(("B.RPP", 1), ("A.RPP-bak", 1), ("A.RPP", 1), ("c.rpp", 1), ("D.RPP", 1, 1))
    assert [p.name for p in project_candidates(files)] == ["A.RPP", "B.RPP", "c.rpp"]


def test_project_candidates_empty_without_one():
    assert project_candidates(_files(("a.wv", 1))) == []


def test_media_to_fetch_takes_only_referenced_files():
    files = _files(
        ("01-Kev Vox.wv", 100),
        ("01-Kev Vox.wv.reapeaks", 5),
        ("mixdown.mp3", 50),
        ("02-Drums.wv", 200),
    )

    fetched = media_to_fetch(files, {"01-Kev Vox.wv", "02-Drums.wv", "old-night.wv"})

    assert [item.name for item in fetched] == ["01-Kev Vox.wv", "02-Drums.wv"]


def test_media_to_fetch_prefers_the_copy_nearest_the_project_then_the_larger():
    nearer = _files(("01-Kev Vox.wv", 900, 1), ("01-Kev Vox.wv", 10, 0))
    same_level = _files(("01-Kev Vox.wv", 10), ("01-Kev Vox.wv", 900))

    assert media_to_fetch(nearer, {"01-Kev Vox.wv"})[0].size == 10
    assert media_to_fetch(same_level, {"01-Kev Vox.wv"})[0].size == 900


# --- downloading ------------------------------------------------------------

def _media_url(file_id):
    return f"{drive_source.DRIVE_FILES_URL}/{file_id}"


def test_download_resumes_from_where_a_dropped_connection_stopped(tmp_path):
    data = bytes(range(256)) * 40
    target = DriveFile(id="wv1", name="a.wv", mime_type="x", size=len(data))
    session = FakeSession({_media_url("wv1"): [
        FakeResponse(content=data, drop_after=1000),
        FakeResponse(status=206, content=data[1000:]),
    ]})

    DriveClient(session).download(target, tmp_path / "a.wv")

    assert (tmp_path / "a.wv").read_bytes() == data
    assert session.calls[1]["headers"]["Range"] == "bytes=1000-"
    assert not (tmp_path / "a.wv.part").exists()


def test_download_starts_over_when_the_server_ignores_the_range(tmp_path):
    data = b"x" * 3000
    target = DriveFile(id="wv1", name="a.wv", mime_type="x", size=len(data))
    session = FakeSession({_media_url("wv1"): [
        FakeResponse(content=data, drop_after=1000),
        FakeResponse(status=200, content=data),
    ]})

    DriveClient(session).download(target, tmp_path / "a.wv")

    assert (tmp_path / "a.wv").read_bytes() == data


def test_download_never_leaves_a_short_file_in_place(tmp_path):
    target = DriveFile(id="wv1", name="a.wv", mime_type="x", size=5000)
    session = FakeSession({_media_url("wv1"): [
        FakeResponse(content=b"x" * 5000, drop_after=100)
        for _ in range(drive_source._DOWNLOAD_ATTEMPTS)
    ]})

    with pytest.raises(DriveError):
        DriveClient(session).download(target, tmp_path / "a.wv")
    assert not (tmp_path / "a.wv").exists()


def test_download_does_not_retry_a_refusal(tmp_path):
    target = DriveFile(id="wv1", name="a.wv", mime_type="x", size=10)
    session = FakeSession({_media_url("wv1"): [
        FakeResponse(status=404, body={"error": {"message": "File not found: wv1."}}),
    ]})

    with pytest.raises(DriveError, match="File not found"):
        DriveClient(session).download(target, tmp_path / "a.wv")
    assert len(session.calls) == 1


def test_download_sends_the_resource_key_of_an_old_link_shared_file(tmp_path):
    target = DriveFile(id="wv1", name="a.wv", mime_type="x", size=3, resource_key="rk")
    session = FakeSession({_media_url("wv1"): [FakeResponse(content=b"abc")]})

    DriveClient(session).download(target, tmp_path / "a.wv")

    assert session.calls[0]["headers"]["X-Goog-Drive-Resource-Keys"] == "wv1/rk"


# --- configuration ----------------------------------------------------------

def test_a_bare_key_name_is_looked_for_in_the_secrets_dir(tmp_path, monkeypatch):
    (tmp_path / "key.json").write_text("{}")
    monkeypatch.setattr(drive_source, "SECRETS_DIR", tmp_path)
    monkeypatch.setenv("GOOGLE_DRIVE_KEY", "key.json")
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "1kFoDGTT8fHU-MKOGewyodOaJT2I-yok6")

    assert drive_source.key_path() == tmp_path / "key.json"
    assert drive_source.configured()


def test_unset_or_missing_key_means_not_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(drive_source, "SECRETS_DIR", tmp_path)
    monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "1kFoDGTT8fHU-MKOGewyodOaJT2I-yok6")

    monkeypatch.delenv("GOOGLE_DRIVE_KEY", raising=False)
    assert not drive_source.configured()

    monkeypatch.setenv("GOOGLE_DRIVE_KEY", "missing.json")
    assert not drive_source.configured()


# --- naming -----------------------------------------------------------------

def test_a_drive_folder_name_keeps_its_dots():
    """A folder has no extension to strip, unlike an uploaded zip's name."""
    from src.api.routers.sessions import parse_session_filename, parse_session_name

    assert parse_session_name("20260612 Vol. 2") == ("Vol. 2", "2026-06-12")
    assert parse_session_name("Loose jam") == ("Loose jam", None)
    assert parse_session_filename(
        "20260501 May the Farts Be With You-20260502T010203Z-1-001.zip"
    ) == ("May the Farts Be With You", "2026-05-01")


# --- choosing between a night's projects ------------------------------------

def _project_text(*media):
    items = "".join(
        f"""    <ITEM
      POSITION {10 * i}
      LENGTH 5
      RECPASS 1
      <SOURCE WAVPACK
        FILE "{name}"
      >
    >
"""
        for i, name in enumerate(media)
    )
    return f"""<REAPER_PROJECT 0.1 "7.39/macOS-arm64" 1780706838
  <TRACK {{AAAA}}
    NAME "1 Kev Vox"
{items}  >
>
"""


class ProjectClient:
    """Downloads write each project's text; nothing else is fetched here."""

    def __init__(self, texts):
        self.texts = texts

    def download(self, item, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.texts[item.name])


async def test_the_project_with_the_most_audio_present_is_scanned(tmp_path):
    from src.api.session_jobs import _choose_drive_project

    files = _files(("1. Warm Up.RPP", 5), ("2. Warm Up.RPP", 5), ("a.wv", 1), ("b.wv", 1))
    client = ProjectClient({
        "1. Warm Up.RPP": _project_text("a.wv", "from-another-night.wv"),
        "2. Warm Up.RPP": _project_text("a.wv", "b.wv"),
    })

    path, media = await _choose_drive_project(
        client, project_candidates(files), files, tmp_path / "projects"
    )

    assert path.name == "2. Warm Up.RPP"
    assert [item.name for item in media] == ["a.wv", "b.wv"]


async def test_a_project_with_nothing_recorded_says_so(tmp_path):
    """The real "20240419 - Nixtamalization" project has no items at all."""
    from src.api.session_jobs import _choose_drive_project

    files = _files(("1. Warm Up.RPP", 5), ("a.wv", 1))
    client = ProjectClient({"1. Warm Up.RPP": _project_text()})

    with pytest.raises(RuntimeError, match="no recorded audio"):
        await _choose_drive_project(
            client, project_candidates(files), files, tmp_path / "projects"
        )
