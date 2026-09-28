"""Read recording sessions straight from the band's shared Google Drive folder.

The band's Reaper projects already live on Drive — one folder per night, named
the way the zips are ("20260501 May the Farts Be With You"), holding the ``.RPP``
and a WavPack file per channel. Importing from there saves a producer from
downloading gigabytes only to upload them again through the browser.

Access is a **service account** with read-only scope. The folder is shared "anyone
with the link can view", so the account needs no invitation of its own; if that
sharing is ever tightened, share the folder with the account's ``client_email``.

Two settings, both read from the environment:

* ``GOOGLE_DRIVE_KEY`` — the service account's JSON key. A bare filename is looked
  for in ``/app/secrets`` (``./secrets`` on the host, see docker-compose); an
  absolute path is used as given. Unset means the feature is simply off.
* ``GOOGLE_DRIVE_FOLDER_ID`` — the folder the sessions are filed under.

Only what the project needs is fetched: the ``.RPP`` first, then the audio files
it actually references. A project folder also carries Reaper's peak caches,
``.RPP-bak`` backups and rendered mixes, none of which a scan reads.

Everything here is synchronous (``requests``) and is called from a threadpool.
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests

logger = logging.getLogger("backend-api")

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
FOLDER_MIME = "application/vnd.google-apps.folder"

#: Where a bare ``GOOGLE_DRIVE_KEY`` filename is looked for (docker-compose).
SECRETS_DIR = Path("/app/secrets")

#: Drive ids are URL-safe base64-ish; anything else is not an id and must never
#: reach the ``q`` search string, where it would change the query.
_DRIVE_ID = re.compile(r"^[A-Za-z0-9_-]{10,}$")

#: Sessions nest a level or two ("July Christie/20250124 - Waitlisted/", or a
#: project's "Audio/"). The bound stops a mis-set root from walking a whole Drive.
_MAX_DEPTH = 4

#: Parallel folder listings when searching for sessions: each is one request.
_LIST_WORKERS = 8

_TIMEOUT = (10, 120)
_CHUNK = 8 * 1024 * 1024
_DOWNLOAD_ATTEMPTS = 4

_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,resourceKey"


class DriveError(RuntimeError):
    """Drive refused or failed a request. The message is safe to show."""


@dataclass(frozen=True)
class DriveFile:
    id: str
    name: str
    mime_type: str
    size: Optional[int] = None
    modified_time: Optional[str] = None
    resource_key: Optional[str] = None

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME

    @classmethod
    def from_api(cls, raw: Dict) -> "DriveFile":
        size = raw.get("size")
        return cls(
            id=raw["id"],
            name=raw["name"],
            mime_type=raw.get("mimeType", ""),
            size=int(size) if size is not None else None,
            modified_time=raw.get("modifiedTime"),
            resource_key=raw.get("resourceKey"),
        )


@dataclass(frozen=True)
class DriveSession:
    """A folder holding a Reaper project: one night's recording."""

    folder: DriveFile
    #: The folders it sits inside, below the root. Empty for a top-level
    #: session; tells two copies of one night filed in different places apart.
    location: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionFile:
    """A file in a session folder, with how deep below it the file sits."""

    file: DriveFile
    depth: int = 0


def key_path() -> Optional[Path]:
    """The service-account key file, or None when Drive import is not set up."""
    value = (os.getenv("GOOGLE_DRIVE_KEY") or "").strip()
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = SECRETS_DIR / path
    return path if path.is_file() else None


def root_folder_id() -> Optional[str]:
    value = (os.getenv("GOOGLE_DRIVE_FOLDER_ID") or "").strip()
    return value if is_drive_id(value) else None


def configured() -> bool:
    return key_path() is not None and root_folder_id() is not None


def is_drive_id(value: str) -> bool:
    return bool(_DRIVE_ID.match(value or ""))


class DriveClient:
    """A read-only Drive session authenticated as the service account."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        if session is None:
            session = _authorized_session()
        self._session = session

    def list_children(self, folder_id: str) -> List[DriveFile]:
        """Every non-trashed item directly inside ``folder_id``."""
        if not is_drive_id(folder_id):
            raise DriveError(f"Not a Drive folder id: {folder_id!r}")
        files: List[DriveFile] = []
        page_token = None
        while True:
            params = {
                "q": f"'{folder_id}' in parents and trashed = false",
                "fields": f"nextPageToken,files({_FILE_FIELDS})",
                "pageSize": 1000,
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if page_token:
                params["pageToken"] = page_token
            response = self._session.get(DRIVE_FILES_URL, params=params, timeout=_TIMEOUT)
            _raise_for_drive(response)
            body = response.json()
            files.extend(DriveFile.from_api(raw) for raw in body.get("files", []))
            page_token = body.get("nextPageToken")
            if not page_token:
                return files

    def download(self, file: DriveFile, dest: Path) -> None:
        """Fetch one file to ``dest``, resuming after a dropped connection.

        Written to ``<dest>.part`` and renamed only once its size matches what
        Drive reports, so a half-fetched track can never pass for a whole one.
        """
        part = dest.with_name(dest.name + ".part")
        part.unlink(missing_ok=True)
        dest.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
            have = part.stat().st_size if part.exists() else 0
            if file.size is not None and have >= file.size:
                break
            headers = _resource_key_header(file)
            if have:
                headers["Range"] = f"bytes={have}-"
            try:
                with self._session.get(
                    f"{DRIVE_FILES_URL}/{file.id}",
                    params={"alt": "media", "supportsAllDrives": "true"},
                    headers=headers,
                    stream=True,
                    timeout=_TIMEOUT,
                ) as response:
                    if _retryable_status(response.status_code):
                        raise requests.ConnectionError(f"HTTP {response.status_code}")
                    _raise_for_drive(response)
                    # A server that ignores Range sends the whole file again.
                    mode = "ab" if have and response.status_code == 206 else "wb"
                    with open(part, mode) as handle:
                        for chunk in response.iter_content(_CHUNK):
                            handle.write(chunk)
                if file.size is None:
                    break
            except (
                requests.ConnectionError,
                requests.Timeout,
                requests.exceptions.ChunkedEncodingError,
            ) as exc:
                if attempt == _DOWNLOAD_ATTEMPTS:
                    raise DriveError(f"Download of {file.name} kept failing: {exc}") from exc
                logger.warning(
                    "Drive download of %s interrupted (attempt %d): %s",
                    file.name, attempt, exc,
                )

        size = part.stat().st_size if part.exists() else 0
        if file.size is not None and size != file.size:
            raise DriveError(
                f"Download of {file.name} is incomplete ({size} of {file.size} bytes)"
            )
        part.replace(dest)


def find_sessions(client: DriveClient, root_id: str) -> List[DriveSession]:
    """Every session folder under the root, at any depth, newest-named first.

    A session is **a folder that directly holds a ``.RPP``**. Sessions are not
    only the root's children: nights get filed inside other nights' folders
    ("20240719 - July Christie" holds seven 2025 sessions), and one night can
    sit in two places. Folders named with a leading underscore ("_Archive")
    are not sessions and are not searched.

    Listed a level at a time in parallel, since each folder is one request.
    Names start with the date (``YYYYMMDD``), so reverse name order is newest
    first without trusting Drive's modified times.
    """
    sessions: List[DriveSession] = []
    pending = [(child, ()) for child in _subfolders(client.list_children(root_id))]
    depth = 1
    with ThreadPoolExecutor(max_workers=_LIST_WORKERS) as pool:
        while pending and depth <= _MAX_DEPTH:
            listings = list(pool.map(lambda entry: client.list_children(entry[0].id), pending))
            deeper = []
            for (folder, location), children in zip(pending, listings):
                if any(_is_project(child) for child in children):
                    sessions.append(DriveSession(folder=folder, location=location))
                deeper.extend(
                    (sub, location + (folder.name,)) for sub in _subfolders(children)
                )
            pending = deeper
            depth += 1
    return sorted(sessions, key=lambda session: session.folder.name, reverse=True)


def session_files(client: DriveClient, folder_id: str) -> List[SessionFile]:
    """The files that belong to one session folder.

    Its own files, plus those in sub-folders that are *not* sessions themselves
    ("Audio/", "Media/"). A sub-folder holding its own ``.RPP`` is another night
    and is left out — its tracks must never be mixed into this one.
    """
    found: List[SessionFile] = []
    pending = [(folder_id, 0)]
    while pending:
        current, depth = pending.pop()
        children = client.list_children(current)
        if depth > 0 and any(_is_project(child) for child in children):
            continue
        for child in children:
            if not child.is_folder:
                found.append(SessionFile(file=child, depth=depth))
            elif depth < _MAX_DEPTH and not _ignored(child.name):
                pending.append((child.id, depth + 1))
    return found


def project_candidates(files: Iterable[SessionFile]) -> List[DriveFile]:
    """The session folder's own Reaper projects, by name.

    Only the folder's own level: a project deeper down belongs to a nested
    session. ``.RPP-bak`` backups are not projects. A night sometimes has two
    ("1. Warm Up.RPP", "2. Warm Up.RPP"); which one to scan is decided by what
    each references (see ``session_jobs.fetch_from_drive``).
    """
    return sorted(
        (entry.file for entry in files if entry.depth == 0 and _is_project(entry.file)),
        key=lambda item: item.name,
    )


def media_to_fetch(
    files: Iterable[SessionFile], wanted_names: Iterable[str]
) -> List[DriveFile]:
    """The files whose basenames the project references, one per name.

    Reaper references media by basename and the scan lays files out flat, so
    two files of the same name cannot both be used. The one nearest the project
    wins, then the larger, since a truncated or placeholder copy is the likelier
    stray.
    """
    wanted = set(wanted_names)
    chosen: Dict[str, SessionFile] = {}
    for entry in files:
        if entry.file.name not in wanted:
            continue
        current = chosen.get(entry.file.name)
        if current is None or _preferred(entry, current):
            chosen[entry.file.name] = entry
    return sorted((entry.file for entry in chosen.values()), key=lambda item: item.name)


def _preferred(candidate: SessionFile, current: SessionFile) -> bool:
    if candidate.depth != current.depth:
        return candidate.depth < current.depth
    return (candidate.file.size or 0) > (current.file.size or 0)


def _is_project(item: DriveFile) -> bool:
    return not item.is_folder and item.name.lower().endswith(".rpp")


def _ignored(name: str) -> bool:
    return name.startswith("_")


def _subfolders(children: Iterable[DriveFile]) -> List[DriveFile]:
    return [child for child in children if child.is_folder and not _ignored(child.name)]
def _authorized_session() -> requests.Session:
    path = key_path()
    if path is None:
        raise DriveError("Google Drive import is not configured (GOOGLE_DRIVE_KEY)")
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        str(path), scopes=SCOPES
    )
    return AuthorizedSession(credentials)


def _resource_key_header(file: DriveFile) -> Dict[str, str]:
    # Link-shared files from before Drive's 2021 security update need their
    # resource key alongside the id, or they read as not found.
    if not file.resource_key:
        return {}
    return {"X-Goog-Drive-Resource-Keys": f"{file.id}/{file.resource_key}"}


def _retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def _raise_for_drive(response: requests.Response) -> None:
    """Turn a Drive error into a ``DriveError`` carrying Google's own message.

    Google's message is the useful part — "Drive API has not been used in
    project … or it is disabled", "File not found" — so it is passed through
    rather than replaced with a generic failure.
    """
    if response.ok:
        return
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:300] or response.reason
    raise DriveError(f"Google Drive error {response.status_code}: {message}")
