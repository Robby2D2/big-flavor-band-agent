"""Scan an unpacked recording session and report the takes found in it.

This is the diagnostic behind session import: it parses the Reaper project,
selects the recording passes whose media actually shipped, scans every track's
loudness envelope, and prints the takes it detected — plus the per-track
measurements the detection rests on, so a wrong answer can be read rather than
guessed at.

    docker exec bigflavor-backend python -m scripts.scan_session \\
        /app/audio_library/sessions/sample/raw

Add ``--plot`` for an activity strip per take, which is the quickest way to see
whether a boundary landed in the right place.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

sys.path.insert(0, "/app")

from src.production import session_attempts, session_transcribe, wavpack_io
from src.production.rpp_parser import Project, RecordingPass, parse_project
from src.production.session_detect import (
    Activity,
    Take,
    Track,
    build_activity,
    detect_takes,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_dir", help="Directory of unpacked session media")
    parser.add_argument("--plot", action="store_true", help="Draw activity strips")
    parser.add_argument(
        "--pass", dest="only_pass", type=int, help="Scan only this RECPASS"
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Transcribe each region and split it into attempts (slow: loads Whisper)",
    )
    parser.add_argument(
        "--transcript-cache",
        help=(
            "JSON file holding this pass's transcript. Read if it exists, written "
            "if not — so labelling can be re-tuned without transcribing again."
        ),
    )
    args = parser.parse_args()

    root = Path(args.session_dir)
    project_files = sorted(root.glob("*.RPP"))
    if not project_files:
        print(f"No .RPP found in {root}")
        return 1

    print(f"Project: {project_files[0].name}")
    project = parse_project(project_files[0])
    media = {path.name: path for path in root.iterdir() if path.is_file()}

    passes = _selectable_passes(project, media)
    if args.only_pass is not None:
        passes = [p for p in passes if p.number == args.only_pass]

    for recording_pass in passes:
        _scan_pass(
            recording_pass,
            media,
            plot=args.plot,
            refine=args.refine,
            cache=args.transcript_cache,
        )

    return 0


def _selectable_passes(project: Project, media: Dict[str, Path]) -> List[RecordingPass]:
    """Report every pass in the project; return those whose media is present.

    A project accumulates sessions, so most passes belong to earlier nights and
    their audio is not in this zip. That is normal and must read as such.
    """
    print(f"Tracks in project: {len(project.track_names)}")
    selectable: List[RecordingPass] = []
    print("\nRecording passes:")
    for recording_pass in project.passes():
        present = sum(1 for item in recording_pass.items if item.source_name in media)
        total = len(recording_pass.items)
        span = f"{_clock(recording_pass.start)}–{_clock(recording_pass.end)}"
        if present == 0:
            print(
                f"  pass {recording_pass.number}: {span} "
                f"({_mins(recording_pass.duration)}) — media not in this upload, skipping"
            )
            continue
        print(
            f"  pass {recording_pass.number}: {span} "
            f"({_mins(recording_pass.duration)}) — {present}/{total} tracks present"
        )
        selectable.append(recording_pass)
    return selectable


def _scan_pass(
    recording_pass: RecordingPass,
    media: Dict[str, Path],
    plot: bool,
    refine: bool = False,
    cache: str | None = None,
) -> None:
    print(f"\n{'=' * 78}\nPASS {recording_pass.number}\n{'=' * 78}")

    started = time.time()
    tracks: List[Track] = []
    for item in sorted(recording_pass.items, key=lambda i: i.position):
        path = media.get(item.source_name)
        if path is None:
            continue
        envelope = wavpack_io.envelope(path)
        tracks.append(
            Track(
                name=item.track_name,
                source_name=item.source_name,
                position=item.position,
                envelope=envelope,
            )
        )
    elapsed = time.time() - started
    audio_seconds = sum(t.envelope.duration for t in tracks)
    print(
        f"Scanned {len(tracks)} tracks ({_mins(audio_seconds)} of audio) "
        f"in {elapsed:.1f}s — {audio_seconds / max(elapsed, 0.001):.0f}x realtime\n"
    )

    print(f"  {'track':34} {'role':7} {'peak':>7} {'active':>7}  offset")
    for track in tracks:
        flags = track.active_frames()
        share = 100.0 * float(np.mean(flags)) if len(flags) else 0.0
        offset = track.position - recording_pass.start
        note = " DEAD" if track.is_dead else ""
        print(
            f"  {track.name[:34]:34} {track.role:7} {track.peak_db:6.1f}dB "
            f"{share:6.1f}%  +{offset:.0f}s{note}"
        )

    activity = build_activity(tracks, fps=wavpack_io.ENVELOPE_FPS)
    takes = detect_takes(activity)

    playing_share = 100.0 * float(np.mean(activity.playing)) if activity.playing.size else 0.0
    print(f"\n  Music detected across {playing_share:.1f}% of the pass")
    print(f"\n  {len(takes)} takes:")
    print(f"  {'#':>3}  {'start':>9} {'end':>9} {'length':>8}")
    for index, take in enumerate(takes, 1):
        tag = "  (fragment)" if take.is_fragment else ""
        print(
            f"  {index:>3}  {_clock(take.start):>9} {_clock(take.end):>9} "
            f"{_mins(take.duration):>8}{tag}"
        )
        if plot:
            print(f"       {_strip(activity, take.start, take.end)}")

    total = sum(take.duration for take in takes)
    print(
        f"\n  {_mins(total)} of regions out of {_mins(recording_pass.duration)} "
        f"({100 * total / max(recording_pass.duration, 1):.0f}% of the pass)"
    )

    if refine:
        _refine_pass(takes, activity, tracks, media, cache)


def _refine_pass(
    regions: List[Take],
    activity: Activity,
    tracks: List[Track],
    media: Dict[str, Path],
    cache: str | None = None,
) -> None:
    """Transcribe each region and report the attempts its words reveal."""
    import asyncio

    from src.llm.llm_provider import get_llm_provider
    from src.rag.lyrics_extractor import LyricsExtractor

    print(f"\n{'-' * 78}")
    print(f"  REFINING {len(regions)} regions from their transcripts")
    print(f"{'-' * 78}")

    # Whisper loads once for the whole pass, not once per region — and not at
    # all when a cached transcript makes it unnecessary.
    extractor = (
        None
        if _cached_transcripts(cache, regions) is not None
        else LyricsExtractor(min_confidence=session_transcribe.SESSION_MIN_CONFIDENCE)
    )
    llm = get_llm_provider()
    workdir = Path("/tmp/session_refine")
    workdir.mkdir(parents=True, exist_ok=True)

    async def run() -> None:
        # Transcribe every region first: the labelling that follows is one call
        # for the whole pass, because judging a line as sung or spoken depends on
        # the other lines it sits beside.
        transcripts = _cached_transcripts(cache, regions)
        if transcripts is None:
            transcripts = []
            for index, region in enumerate(regions, 1):
                vocal_path = session_transcribe.build_vocal_mix(
                    region, tracks, media, workdir / f"region{index:02d}.wav"
                )
                if vocal_path is None:
                    print(f"  region {index}: no vocal tracks — kept whole")
                    transcripts.append((region, []))
                    continue
                lines = session_transcribe.transcribe_region(
                    vocal_path, region, extractor
                )
                print(f"  region {index}: {len(lines)} transcribed lines")
                transcripts.append((region, lines))
            _write_transcripts(cache, transcripts)
        else:
            print(f"  (transcript read from {cache})")

        per_region = await session_attempts.attempts_for_regions(
            transcripts, llm, activity=activity
        )

        found = 0
        for index, ((region, lines), attempts) in enumerate(
            zip(transcripts, per_region), 1
        ):
            found += len(attempts)
            sung = {id(line) for a in attempts for line in a.lines}
            print(
                f"\n  region {index} ({_clock(region.start)}-{_clock(region.end)}, "
                f"{_mins(region.duration)}): {len(lines)} lines -> "
                f"{len(attempts)} attempts"
            )
            for line in lines:
                mark = "SUNG" if id(line) in sung else "talk"
                print(f"      {mark} [{_clock(line.start)}] {line.text[:66]}")
            for number, attempt in enumerate(attempts, 1):
                print(
                    f"      -> attempt {number}: {_clock(attempt.take.start)}-"
                    f"{_clock(attempt.take.end)} ({_mins(attempt.take.duration)})"
                )
        print(f"\n  {found} attempts across the pass")

    asyncio.run(run())


def _cached_transcripts(cache: str | None, regions: List[Take]):
    """Read a cached transcript, or None when there is nothing usable to read."""
    if not cache or not Path(cache).exists():
        return None
    import json

    payload = json.loads(Path(cache).read_text(encoding="utf-8"))
    if len(payload) != len(regions):
        print(f"  (cache {cache} covers {len(payload)} regions, not {len(regions)})")
        return None
    return [
        (
            region,
            [
                session_transcribe.TranscriptLine(
                    start=entry["start"],
                    end=entry["end"],
                    text=entry["text"],
                    confidence=entry.get("confidence", 0.0),
                )
                for entry in held
            ],
        )
        for region, held in zip(regions, payload)
    ]


def _write_transcripts(cache: str | None, transcripts) -> None:
    if not cache:
        return
    import json

    payload = [
        [
            {
                "start": line.start,
                "end": line.end,
                "text": line.text,
                "confidence": line.confidence,
            }
            for line in lines
        ]
        for _, lines in transcripts
    ]
    Path(cache).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"  (transcript written to {cache})")


def _strip(activity: Activity, start: float, end: float, width: int = 60) -> str:
    """A coarse activity bar for one take, to eyeball where music actually sits."""
    begin = int((start - activity.start) * activity.fps)
    finish = int((end - activity.start) * activity.fps)
    window = activity.playing[max(begin, 0) : finish]
    if window.size == 0:
        return ""
    buckets = np.array_split(window, min(width, window.size))
    return "".join(
        "#" if bucket.mean() > 0.66 else ("-" if bucket.mean() > 0.2 else ".")
        for bucket in buckets
    )


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _mins(seconds: float) -> str:
    return f"{int(seconds) // 60}m{int(seconds) % 60:02d}s"


if __name__ == "__main__":
    raise SystemExit(main())
