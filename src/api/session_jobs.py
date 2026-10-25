"""Background runner for recording-session import.

Scanning a rehearsal session takes tens of minutes — a 2 GB upload to unpack, an
hour of multitrack audio to measure, and Whisper over every stretch the band
played — so it runs as a background task the producer polls, like
``stem_jobs.py``.

Unlike the stem runner, the *narration* is durable too: ``recording_sessions``
carries ``stage`` and ``progress`` as well as ``status``, because a scan outlives
a request by many minutes and a page reloaded mid-run has to pick the story back
up rather than show a blank.

Stage order is chosen so nothing is rendered twice. Boundaries cannot be settled
until the words are known (see ``session_attempts``), and rendering a take means
slicing every channel, so transcription comes first and the audio is cut once.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from fastapi.concurrency import run_in_threadpool

from database import DatabaseManager
from src.llm.llm_provider import get_llm_provider
from src.production import (
    drive_source,
    session_attempts,
    session_detect,
    session_grouping,
    session_render,
    session_transcribe,
    waveform_peaks,
    wavpack_io,
)
from src.production.rpp_parser import (
    MIXDOWN_SOURCE,
    RECORDING_SUFFIXES,
    Project,
    RecordingPass,
    parse_project,
    project_from_recordings,
)

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

STAGE_DOWNLOADING = "downloading"
STAGE_UNPACKING = "unpacking"
STAGE_SCANNING = "scanning"
STAGE_TRANSCRIBING = "transcribing"
STAGE_RENDERING = "rendering"

#: Zip members we refuse to extract. `.RPP-bak` is Reaper's own backup of the
#: project and would be picked up as a second project file.
_SKIP_SUFFIXES = (".rpp-bak",)

#: An upper bound on what one session may unpack to, so a hostile or accidental
#: zip cannot fill the disk. A real 4.5-hour session measured 2 GB.
MAX_UNPACKED_BYTES = 40 * 1024**3


@dataclass
class _PassScan:
    """One recording pass, measured and ready to cut into takes."""

    recording_pass: RecordingPass
    tracks: List[session_detect.Track]
    activity: session_detect.Activity
    regions: List[session_detect.Take]


class SessionJobManager:
    """Tracks running session scans; durable state lives in the DB."""

    def __init__(self) -> None:
        # session_id -> Task, so a job isn't garbage-collected while it runs.
        self._tasks: Dict[int, asyncio.Task] = {}
        # Takes whose words are queued or being read again after a split, and
        # the tasks reading them. One read at a time: each loads Whisper.
        self._listening: set[int] = set()
        self._listen_tasks: set[asyncio.Task] = set()
        self._listen_lock = asyncio.Lock()

    def start(self, session_id: int, zip_path: str, db: DatabaseManager) -> None:
        """Kick off the scan of an uploaded session."""

        async def unpack(raw_dir: Path) -> None:
            await _stage(db, session_id, STAGE_UNPACKING, 0)
            await run_in_threadpool(unpack_session, zip_path, raw_dir)

        self._launch(session_id, db, unpack)

    def start_from_drive(
        self, session_id: int, folder_id: str, db: DatabaseManager
    ) -> None:
        """Kick off the scan of a session read from its Google Drive folder."""

        async def download(raw_dir: Path) -> None:
            await fetch_from_drive(db, session_id, folder_id, raw_dir)

        self._launch(session_id, db, download)

    def is_running(self, session_id: int) -> bool:
        return session_id in self._tasks

    def listen(self, db: DatabaseManager, takes: Sequence[Dict]) -> None:
        """Read the words of takes marked ``transcript_pending``, in the background.

        Takes already queued are skipped, so it is safe to call on every page
        load — which is how a read cut short by a restart picks back up.
        """
        fresh = [take for take in takes if take["id"] not in self._listening]
        if not fresh:
            return
        self._listening.update(take["id"] for take in fresh)
        task = asyncio.create_task(self._listen(db, fresh))
        self._listen_tasks.add(task)
        task.add_done_callback(self._listen_tasks.discard)

    async def _listen(self, db: DatabaseManager, takes: Sequence[Dict]) -> None:
        try:
            async with self._listen_lock:
                extractor = await run_in_threadpool(_load_extractor)
                for take in takes:
                    await _read_take_words(db, take, extractor)
        except Exception:
            logger.exception("Could not read the words of split takes")
        finally:
            self._listening.difference_update(take["id"] for take in takes)

    def _launch(self, session_id: int, db: DatabaseManager, gather) -> None:
        task = asyncio.create_task(self._run(session_id, db, gather))
        self._tasks[session_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(session_id, None))

    async def _run(self, session_id: int, db: DatabaseManager, gather) -> None:
        """Run one session scan end to end. Never raises.

        ``gather`` puts the session's ``.RPP`` and media — or its plain
        recordings — into ``raw_dir``, by unpacking an uploaded zip or by
        downloading from Drive, and owns the first 10% of progress. Everything
        after it is the same scan.
        """
        raw_dir = session_dir(session_id) / "raw"
        try:
            await gather(raw_dir)

            project = await run_in_threadpool(load_project, raw_dir)
            media = {path.name: path for path in raw_dir.iterdir() if path.is_file()}
            passes = selectable_passes(project, media)
            if not passes:
                raise RuntimeError(
                    "No recording pass in this project has its audio in the upload"
                )

            await _stage(db, session_id, STAGE_SCANNING, 10)
            scans = []
            for index, recording_pass in enumerate(passes):
                scans.append(await _scan_pass(recording_pass, media, db, session_id))
                await _stage(
                    db, session_id, STAGE_SCANNING,
                    10 + int(25 * (index + 1) / len(passes)),
                )

            await _record_session_shape(db, session_id, raw_dir, scans, media)

            await _stage(db, session_id, STAGE_TRANSCRIBING, 35)
            extractor = await run_in_threadpool(_load_extractor)
            llm = get_llm_provider()
            attempts_by_pass = []
            for index, scan in enumerate(scans):
                attempts_by_pass.append(
                    await _attempts_for(scan, media, extractor, llm, session_id)
                )
                await _stage(
                    db, session_id, STAGE_TRANSCRIBING,
                    35 + int(35 * (index + 1) / len(scans)),
                )

            await _stage(db, session_id, STAGE_RENDERING, 70)
            total = sum(len(attempts) for attempts in attempts_by_pass) or 1
            done = 0
            for scan, attempts in zip(scans, attempts_by_pass):
                for attempt in attempts:
                    await _store_take(db, session_id, scan, attempt, media)
                    done += 1
                    await _stage(
                        db, session_id, STAGE_RENDERING, 70 + int(29 * done / total)
                    )

            await group_session_takes(db, session_id)

            # The raw WavPack is the bulk of the disk and nothing downstream reads
            # it again: the takes carry their own audio.
            await run_in_threadpool(shutil.rmtree, raw_dir, True)
            await db.clear_recording_session_raw_dir(session_id)
            _remove_quietly(upload_zip_path(session_id))

            await db.set_recording_session_status(
                session_id, STATUS_COMPLETE, stage=None, progress=100
            )
            logger.info("Session %s scanned: %d takes", session_id, done)
        except Exception as exc:
            logger.exception("Session scan failed for session %s", session_id)
            await db.set_recording_session_status(
                session_id, STATUS_FAILED, error=str(exc)
            )


async def _stage(
    db: DatabaseManager, session_id: int, stage: str, progress: int
) -> None:
    await db.set_recording_session_status(
        session_id, STATUS_RUNNING, stage=stage, progress=progress
    )


def unpack_session(zip_path: str | Path, raw_dir: Path) -> None:
    """Extract a session zip's audio and project file, flat, into ``raw_dir``.

    Members are written by **basename only**: Reaper references its media by
    basename, a Google Drive export nests everything under a folder, and
    flattening is also what makes path traversal impossible — no member can
    escape ``raw_dir`` because no member keeps its path.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name or name.lower().endswith(_SKIP_SUFFIXES):
                continue
            written += info.file_size
            if written > MAX_UNPACKED_BYTES:
                raise RuntimeError(
                    f"Session unpacks to more than {MAX_UNPACKED_BYTES // 1024**3} GB"
                )
            with archive.open(info) as source, open(raw_dir / name, "wb") as target:
                shutil.copyfileobj(source, target, length=8 * 1024 * 1024)


async def fetch_from_drive(
    db: DatabaseManager, session_id: int, folder_id: str, raw_dir: Path
) -> None:
    """Download a session's project and the audio it references into ``raw_dir``.

    The ``.RPP`` comes first because it says which files matter: a project
    folder also holds peak caches, backups and renders, and a project that has
    accumulated several nights references media from other folders that is
    simply absent here — the same as a zip that did not carry it.

    A folder with no project is a night recorded some other way, and its plain
    recordings (mp3 and the like) are downloaded as they are.
    """
    await _stage(db, session_id, STAGE_DOWNLOADING, 0)
    client = await run_in_threadpool(drive_source.DriveClient)
    files = await run_in_threadpool(drive_source.session_files, client, folder_id)

    candidates = drive_source.project_candidates(files)
    raw_dir.mkdir(parents=True, exist_ok=True)
    if candidates:
        project_path, media = await _choose_drive_project(
            client, candidates, files, raw_dir.parent / "projects"
        )
        if not media:
            raise RuntimeError(
                "None of the audio this project uses is in its Drive folder"
            )
        # Only the chosen project goes into raw_dir, so the scan cannot pick another.
        project_path.replace(raw_dir / project_path.name)
        shutil.rmtree(project_path.parent, ignore_errors=True)
        source = project_path.name
    else:
        media = drive_source.recording_candidates(files)
        if not media:
            raise RuntimeError(
                "No Reaper project (.RPP) or recordings (mp3, wav, …) in this "
                "Drive folder"
            )
        source = "its plain recordings"

    total = sum(item.size or 0 for item in media)
    if total > MAX_UNPACKED_BYTES:
        raise RuntimeError(
            f"Session is more than {MAX_UNPACKED_BYTES // 1024**3} GB of audio"
        )

    logger.info(
        "Session %s: downloading %d files (%.1f GB) from Drive for %s",
        session_id, len(media), total / 1024**3, source,
    )
    # One file at a time so progress can be written between them; a night's
    # tracks are a few hundred MB each, so the bar still moves steadily.
    done = 0
    for item in media:
        await run_in_threadpool(client.download, item, raw_dir / item.name)
        done += item.size or 0
        await _stage(
            db, session_id, STAGE_DOWNLOADING, int(10 * done / total) if total else 10
        )


async def _choose_drive_project(
    client: "drive_source.DriveClient",
    candidates: List["drive_source.DriveFile"],
    files: List["drive_source.SessionFile"],
    staging: Path,
) -> tuple[Path, List["drive_source.DriveFile"]]:
    """Pick which of a folder's projects to scan: the one with the most audio here.

    A night sometimes has two projects side by side ("1. Warm Up.RPP" and
    "2. Warm Up.RPP"). Each is a few MB, so all are read and the one that
    references the most files actually present wins; a tie keeps the first by
    name, which is what a zip upload would scan.
    """
    staging.mkdir(parents=True, exist_ok=True)
    best: Optional[tuple[Path, List[drive_source.DriveFile]]] = None
    any_recorded = False
    for candidate in candidates:
        path = staging / candidate.name
        await run_in_threadpool(client.download, candidate, path)
        project = await run_in_threadpool(parse_project, path)
        referenced = {
            item.source_name
            for recording_pass in project.passes()
            for item in recording_pass.items
        }
        any_recorded = any_recorded or bool(referenced)
        media = drive_source.media_to_fetch(files, referenced)
        if best is None or len(media) > len(best[1]):
            best = (path, media)

    if not any_recorded:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError(
            "This folder's Reaper project has no recorded audio in it — it was "
            "saved before anything was recorded, or the recording is elsewhere"
        )
    return best


def load_project(raw_dir: Path) -> Project:
    """The session's project: its ``.RPP``, or one stood in for its recordings.

    A session with no project is a night recorded some other way — a couple of
    mp3s of the room — and each recording is scanned as one whole-band track.
    """
    projects = sorted(
        path for path in raw_dir.iterdir() if path.suffix.lower() == ".rpp"
    )
    if projects:
        return parse_project(projects[0])

    recordings = []
    for path in sorted(raw_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in RECORDING_SUFFIXES:
            continue
        try:
            recordings.append((path.name, wavpack_io.probe(path).duration))
        except wavpack_io.DecodeError:
            logger.warning("Skipping unreadable recording %s", path.name)
    if not recordings:
        raise RuntimeError(
            "No Reaper project (.RPP) or recordings (mp3, wav, …) in this upload"
        )
    return project_from_recordings(recordings)


def selectable_passes(project, media: Dict[str, Path]) -> List[RecordingPass]:
    """The passes whose media this upload actually carried.

    A project accumulates sessions, so most of its passes belong to earlier
    nights and point at files in other project folders. Their absence is normal.
    """
    return [
        recording_pass
        for recording_pass in project.passes()
        if any(item.source_name in media for item in recording_pass.items)
    ]


async def _scan_pass(
    recording_pass: RecordingPass,
    media: Dict[str, Path],
    db: DatabaseManager,
    session_id: int,
) -> _PassScan:
    """Measure every present track of one pass and find its candidate regions."""
    tracks: List[session_detect.Track] = []
    for item in sorted(recording_pass.items, key=lambda i: i.position):
        path = media.get(item.source_name)
        if path is None:
            continue
        envelope = await run_in_threadpool(wavpack_io.envelope, path)
        track = session_detect.Track(
            name=item.track_name or item.source_name,
            source_name=item.source_name,
            position=item.position,
            envelope=envelope,
            role=(
                session_detect.MIX_ROLE
                if item.source_type == MIXDOWN_SOURCE
                else "other"
            ),
        )
        tracks.append(track)
        await db.add_session_track(
            session_id=session_id,
            name=track.name,
            source_name=track.source_name,
            role=track.role,
            rec_pass=recording_pass.number,
            position_seconds=track.position,
            peak_db=_finite(track.peak_db),
            is_dead=track.is_dead,
        )

    activity = session_detect.build_activity(tracks, fps=wavpack_io.ENVELOPE_FPS)
    return _PassScan(
        recording_pass=recording_pass,
        tracks=[t for t in tracks if not t.is_dead],
        activity=activity,
        regions=session_detect.detect_takes(activity),
    )


async def _record_session_shape(
    db: DatabaseManager,
    session_id: int,
    raw_dir: Path,
    scans: Sequence[_PassScan],
    media: Dict[str, Path],
) -> None:
    """Store what the upload turned out to contain."""
    sample_rate = None
    for scan in scans:
        for track in scan.tracks:
            path = media.get(track.source_name)
            if path is None:
                continue
            try:
                sample_rate = (await run_in_threadpool(wavpack_io.probe, path)).sample_rate
                break
            except wavpack_io.DecodeError:
                continue
        if sample_rate:
            break

    duration = sum(scan.recording_pass.duration for scan in scans)
    await db.set_recording_session_scan(
        session_id=session_id,
        raw_dir=str(raw_dir),
        rec_passes=[scan.recording_pass.number for scan in scans],
        sample_rate=sample_rate,
        duration_seconds=int(duration),
    )


async def _attempts_for(
    scan: _PassScan,
    media: Dict[str, Path],
    extractor,
    llm,
    session_id: int,
) -> List[session_attempts.Attempt]:
    """Transcribe a pass's regions and split them into attempts."""
    workdir = Path("/tmp") / f"session{session_id}" / f"pass{scan.recording_pass.number}"
    workdir.mkdir(parents=True, exist_ok=True)

    transcripts = []
    for index, region in enumerate(scan.regions, 1):
        vocal_mix = await run_in_threadpool(
            session_transcribe.build_vocal_mix,
            region, scan.tracks, media, workdir / f"region{index:02d}.wav",
        )
        if vocal_mix is None:
            transcripts.append((region, []))
            continue
        lines = await run_in_threadpool(
            session_transcribe.transcribe_region, vocal_mix, region, extractor
        )
        transcripts.append((region, lines))

    shutil.rmtree(workdir, ignore_errors=True)
    per_region = await session_attempts.attempts_for_regions(
        transcripts, llm, activity=scan.activity
    )
    return [attempt for attempts in per_region for attempt in attempts]


async def _store_take(
    db: DatabaseManager,
    session_id: int,
    scan: _PassScan,
    attempt: session_attempts.Attempt,
    media: Dict[str, Path],
) -> None:
    """Render one attempt's audio and record it with its stems."""
    take = await db.add_session_take(
        session_id=session_id,
        rec_pass=scan.recording_pass.number,
        start_seconds=attempt.take.start,
        end_seconds=attempt.take.end,
        transcript=attempt.text or None,
        mix_path=None,
    )

    output_dir = take_dir(session_id, take["id"])
    rendered = await run_in_threadpool(
        session_render.render_take,
        attempt.take, scan.tracks, media, output_dir,
    )

    # A stem is linked back to the channel it came from by that channel's own
    # name within this pass, which is what render_take carries as display_name.
    track_ids = {
        (row["name"], row["rec_pass"]): row["id"]
        for row in await db.list_session_tracks(session_id)
    }
    for stem in rendered.stems:
        if stem.name.split("-")[0] == session_detect.MIX_ROLE:
            # A whole-band recording is the take itself, not one of its parts.
            # Kept as a stem it would become a one-stem set on the produced
            # version and stand in the way of separating it for real.
            _remove_quietly(Path(stem.path))
            continue
        row = await db.add_session_take_stem(
            take_id=take["id"],
            track_id=track_ids.get((stem.display_name, scan.recording_pass.number)),
            name=stem.name,
            display_name=stem.display_name,
            path=stem.path,
            peak_db=_finite(stem.peak_db),
        )
        await _warm_peaks(
            db.set_session_take_stem_waveform_peaks, row["id"], stem.path
        )

    await db.set_session_take_mix_path(take["id"], rendered.mix_path)
    await _warm_peaks(
        db.set_session_take_waveform_peaks, take["id"], rendered.mix_path
    )


async def split_take(
    db: DatabaseManager, take: Dict, at_seconds: float
) -> List[Dict]:
    """Cut one take in two at ``at_seconds`` into it (SESS-22).

    The first half stays in the take's song; the second starts a song of its
    own, since the reason to split is that the band ran one song into the next.
    A take on its own splits into two takes on their own. Both keep the take's
    discard state. Their words are read again in the background — the scan
    kept what was sung, not when — so each starts ``transcript_pending``.

    The halves are new takes with new audio, and the original is deleted only
    once both are written, so a failure leaves the take as it was. The caller
    releases a produced take from the catalog first.
    """
    session_id = take["session_id"]
    start, end = take["start_seconds"], take["end_seconds"]
    second_group = None
    if take.get("group_id") is not None:
        second_group = (await db.create_session_take_group(session_id))["id"]

    halves = [
        await db.add_session_take(
            session_id=session_id,
            rec_pass=take.get("rec_pass"),
            start_seconds=bounds[0],
            end_seconds=bounds[1],
            transcript=None,
            mix_path=None,
            group_id=group_id,
            excluded=take.get("excluded", False),
            transcript_pending=True,
        )
        for bounds, group_id in (
            ((start, start + at_seconds), take.get("group_id")),
            ((start + at_seconds, end), second_group),
        )
    ]
    old_stems = take.get("stems") or []
    try:
        parts = await run_in_threadpool(
            session_render.split_rendered_take,
            take["mix_path"],
            [
                session_render.RenderedStem(
                    name=stem["name"],
                    display_name=stem.get("display_name") or stem["name"],
                    path=stem["path"],
                    peak_db=stem.get("peak_db") or 0.0,
                )
                for stem in old_stems
            ],
            at_seconds,
            take_dir(session_id, halves[0]["id"]),
            take_dir(session_id, halves[1]["id"]),
        )
    except Exception:
        # Deleting the halves also drops the new group, which is left empty.
        for half in halves:
            await db.set_session_take_group_id(half["id"], None)
            await db.delete_session_take(half["id"])
            await run_in_threadpool(
                shutil.rmtree, take_dir(session_id, half["id"]), True
            )
        raise

    track_ids = {stem["name"]: stem.get("track_id") for stem in old_stems}
    for half, part in zip(halves, parts):
        for stem in part.stems:
            row = await db.add_session_take_stem(
                take_id=half["id"],
                track_id=track_ids.get(stem.name),
                name=stem.name,
                display_name=stem.display_name,
                path=stem.path,
                peak_db=_finite(stem.peak_db),
            )
            await _warm_peaks(
                db.set_session_take_stem_waveform_peaks, row["id"], stem.path
            )
        await db.set_session_take_mix_path(half["id"], part.mix_path)
        await _warm_peaks(db.set_session_take_waveform_peaks, half["id"], part.mix_path)

    await db.delete_session_take(take["id"])
    await run_in_threadpool(shutil.rmtree, take_dir(session_id, take["id"]), True)
    logger.info(
        "Take %s split at %.1fs into takes %s and %s",
        take["id"], at_seconds, halves[0]["id"], halves[1]["id"],
    )

    by_id = {row["id"]: row for row in await db.list_session_takes(session_id)}
    split = [by_id[half["id"]] for half in halves]
    manager.listen(db, split)
    return split


async def _read_take_words(db: DatabaseManager, take: Dict, extractor) -> None:
    """Transcribe one take from its own audio and store the words.

    The same sources the scan reads (``session_transcribe.VOICE_ROLES``): the
    singers' mics, or — for a night recorded as plain room recordings, whose
    takes carry no channels — the take itself. A take whose channels hold no
    mic has no words, which is a real answer. A failure stores none rather than
    leaving the take waiting forever.
    """
    stems = take.get("stems") or []
    sources = [
        stem["path"] for stem in stems
        if stem["name"].split("-")[0] in session_transcribe.VOICE_ROLES
    ]
    if not stems and take.get("mix_path"):
        sources = [take["mix_path"]]

    transcript = None
    try:
        if sources:
            transcript = await run_in_threadpool(
                _transcribe_files, sources, extractor, take["id"]
            )
    except Exception:
        logger.exception("Reading the words of take %s failed", take["id"])
    await db.set_session_take_transcript(take["id"], transcript or None)


def _transcribe_files(paths: Sequence[str], extractor, take_id: int) -> str:
    """Sum the given files and return what Whisper hears in them."""
    import soundfile as sf

    workdir = Path("/tmp") / f"take{take_id}-words"
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        audio = Path(paths[0])
        if len(paths) > 1:
            audio = workdir / "voices.wav"
            session_render.mix_audio_files(
                paths, audio, sf.info(str(paths[0])).samplerate
            )
        # Timed from zero: only the words are kept, not where they fall.
        lines = session_transcribe.transcribe_region(
            audio, session_detect.Take(start=0.0, end=0.0), extractor
        )
        return " ".join(line.text for line in lines).strip()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def group_session_takes(db: DatabaseManager, session_id: int) -> int:
    """Guess which of a session's takes are attempts at the same song.

    Runs on the transcripts already stored, so it needs no audio and can be
    re-run on a session scanned before grouping existed. Any previous grouping is
    dropped first — including a producer's names, which is why re-running it is
    a deliberate action and never automatic. A group already produced into the
    catalog survives, and its takes are not guessed again.
    """
    await db.clear_session_take_groups(session_id)
    produced_groups = {
        group["id"]
        for group in await db.list_session_take_groups(session_id)
        if group.get("song_id") is not None
    }
    takes = [
        take for take in await db.list_session_takes(session_id)
        if take.get("group_id") not in produced_groups
    ]
    groups = session_grouping.group_takes(takes)

    for ids in groups:
        group = await db.create_session_take_group(session_id)
        for take_id in ids:
            await db.set_session_take_group_id(take_id, group["id"])

    in_groups, alone = session_grouping.split_counts(takes, groups)
    logger.info(
        "Session %s: %d takes -> %d groups (%d grouped, %d on their own)",
        session_id, len(takes), len(groups), in_groups, alone,
    )
    return len(groups)


async def _warm_peaks(setter, row_id: int, audio_path: str) -> None:
    """Precompute a drawing envelope. Best-effort, like ``stem_jobs``.

    The endpoint computes any that are missing, so a failure here only decides
    whether the first page open pays for it — never whether the take is usable.
    """
    try:
        peaks = await run_in_threadpool(waveform_peaks.compute_peaks, audio_path)
        await setter(row_id, peaks)
    except Exception:
        logger.exception("Waveform peaks failed for %s", audio_path)


def session_dir(session_id: int) -> Path:
    """Where one session's material lives. Writable (see docker-compose)."""
    return Path("/app/audio_library/sessions") / str(session_id)


def upload_zip_path(session_id: int) -> Path:
    """Where a browser upload is assembled from its chunks."""
    return session_dir(session_id) / "upload.zip"


def take_dir(session_id: int, take_id: int) -> Path:
    return session_dir(session_id) / "takes" / str(take_id)


def _load_extractor():
    """Build the Whisper extractor once per session scan.

    Nothing is filtered by confidence: mumbled chatter is exactly the signal that
    separates two attempts, so dropping it would hide the boundaries.
    """
    from src.rag.lyrics_extractor import LyricsExtractor

    return LyricsExtractor(
        min_confidence=session_transcribe.SESSION_MIN_CONFIDENCE
    )


def _finite(value: float) -> Optional[float]:
    """A peak of -inf (a silent track) is not storable as a real; None is."""
    return None if value in (float("inf"), float("-inf")) else value


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove %s", path)


# Single process-wide manager instance the routes consult.
manager = SessionJobManager()
