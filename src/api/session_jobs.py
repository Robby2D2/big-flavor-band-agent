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
    session_attempts,
    session_detect,
    session_render,
    session_transcribe,
    waveform_peaks,
    wavpack_io,
)
from src.production.rpp_parser import RecordingPass, parse_project

logger = logging.getLogger("backend-api")

STATUS_RUNNING = "running"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"

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

    def start(self, session_id: int, zip_path: str, db: DatabaseManager) -> None:
        """Kick off the scan of an uploaded session."""
        task = asyncio.create_task(self._run(session_id, zip_path, db))
        self._tasks[session_id] = task
        task.add_done_callback(lambda _t: self._tasks.pop(session_id, None))

    def is_running(self, session_id: int) -> bool:
        return session_id in self._tasks

    async def _run(self, session_id: int, zip_path: str, db: DatabaseManager) -> None:
        """Run one session scan end to end. Never raises."""
        raw_dir = Path(zip_path).parent / "raw"
        try:
            await _stage(db, session_id, STAGE_UNPACKING, 0)
            await run_in_threadpool(unpack_session, zip_path, raw_dir)

            project_file = _find_project(raw_dir)
            project = await run_in_threadpool(parse_project, project_file)
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

            # The raw WavPack is the bulk of the disk and nothing downstream reads
            # it again: the takes carry their own audio.
            await run_in_threadpool(shutil.rmtree, raw_dir, True)
            await db.clear_recording_session_raw_dir(session_id)
            _remove_quietly(Path(zip_path))

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


def _find_project(raw_dir: Path) -> Path:
    projects = sorted(raw_dir.glob("*.RPP"))
    if not projects:
        raise RuntimeError("No Reaper project (.RPP) in this upload")
    return projects[0]


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
