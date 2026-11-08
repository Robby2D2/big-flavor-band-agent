"""Correct stored lyric timings whose lines light up before they are sung.

Whisper stretches a line's first word back over the silence before it. New
extractions correct that as they run; this applies the same correction to
timings already stored. Nothing is transcribed and the lyric text is not
touched. By default it covers songs with a vocal stem still on disk, which takes
seconds per song. A corrected song has nothing left to move, so it is safe to
run again.

``--separate`` also covers songs whose vocals were discarded, running Demucs on
each. That is a long run, so finished songs are recorded in a small JSON ledger
and skipped next time: to resume, run the same command again. Failed songs are
not recorded, so they are retried. Running it in the background keeps it going
if the terminal closes; a stopped run loses at most the song in progress.

    docker exec bigflavor-backend python -m scripts.snap_lyric_timings --dry-run
    docker exec bigflavor-backend python -m scripts.snap_lyric_timings
    docker exec bigflavor-backend python -m scripts.snap_lyric_timings --song-id 917
    docker exec bigflavor-backend python -m scripts.snap_lyric_timings --separate --limit 3
    docker exec -d bigflavor-backend sh -c \
        'python -m scripts.snap_lyric_timings --separate > /tmp/snap.log 2>&1'
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import List, Optional, Set

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from scripts.backfill_lyric_timings import resolve_audio_path
from src.api import lyrics_jobs

DEFAULT_LEDGER = project_root / "lyric_snap_done.json"

# Quieten the per-song extractor chatter; the script prints its own progress.
logging.getLogger("lyrics-extractor").setLevel(logging.WARNING)


def load_done(path: Path) -> Set[int]:
    """Songs a previous --separate run finished, or none if absent/corrupt."""
    try:
        return set(json.loads(path.read_text(encoding="utf-8"))["done"])
    except (OSError, ValueError, KeyError, TypeError):
        return set()


def save_done(path: Path, done: Set[int]) -> None:
    """Persist the ledger. Losing it only means separating some songs again."""
    path.write_text(json.dumps({"done": sorted(done)}), encoding="utf-8")


def build_separator():
    """The one extractor the run shares, with Demucs loaded and Whisper not."""
    from src.rag.lyrics_extractor import LyricsExtractor

    extractor = LyricsExtractor(whisper_model_size=None, use_gpu=True, load_demucs=True)
    if extractor.demucs is None:
        raise RuntimeError("Demucs is unavailable. Run this inside bigflavor-backend.")
    return extractor


async def snap(
    song_ids: Optional[List[int]],
    dry_run: bool,
    separate: bool = False,
    limit: Optional[int] = None,
    ledger_path: Path = DEFAULT_LEDGER,
) -> int:
    """Run the correction. Returns a process exit code."""
    db = DatabaseManager()
    await db.connect()
    try:
        coverage = await db.list_lyric_timing_coverage()
        wanted = set(song_ids or [])
        done = load_done(ledger_path) if separate else set()
        songs = [
            row for row in coverage
            if row["has_timings"]
            and (not wanted or row["id"] in wanted)
            and row["id"] not in done
        ]
        if limit:
            songs = songs[:limit]

        extractor = build_separator() if separate else None
        if separate:
            print(f"{len(done)} songs already done; {len(songs)} to process.", flush=True)

        changed, lines_moved, skipped, failed = 0, 0, 0, 0
        run_start = time.time()
        for index, row in enumerate(songs, 1):
            song_id = row["id"]
            audio_path = resolve_audio_path(song_id) if separate else None
            try:
                summary = await lyrics_jobs.snap_stored_timings(
                    song_id,
                    db,
                    dry_run=dry_run,
                    audio_path=str(audio_path) if audio_path else None,
                    extractor=extractor,
                )
            except Exception as exc:
                failed += 1
                print(f"  {song_id:>8}  FAILED: {exc}", flush=True)
                continue
            if summary is None:
                skipped += 1
                continue
            shift_ms = (
                round(statistics.median(summary["shifts"]) * 1000) if summary["shifts"] else 0
            )
            print(
                f"  [{index}/{len(songs)}] {song_id:>8}  {(row['title'] or '')[:40]:<42}"
                f"{summary['moved']:>3}/{summary['line_count']:<3} lines"
                f"  median +{shift_ms} ms  {time.time() - run_start:.0f}s",
                flush=True,
            )
            changed += 1 if summary["moved"] else 0
            lines_moved += summary["moved"]
            if separate and not dry_run:
                done.add(song_id)
                save_done(ledger_path, done)

        verb = "would change" if dry_run else "changed"
        print(f"\n{verb} {changed} songs, {lines_moved} lines.")
        print(f"Skipped {skipped} songs with stale timings or no vocals to read.")
        print(f"Failed: {failed}.")
        return 1 if failed else 0
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Correct stored lyric timings against each song's vocals."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would move; change nothing")
    parser.add_argument("--song-id", type=int, action="append", dest="song_ids",
                        help="Process exactly this song (repeatable)")
    parser.add_argument("--separate", action="store_true",
                        help="Run Demucs on songs with no vocal stem on disk (slow)")
    parser.add_argument("--limit", type=int,
                        help="Process at most N songs this run")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                        help=f"Where --separate records finished songs (default: {DEFAULT_LEDGER.name})")
    args = parser.parse_args()
    return asyncio.run(snap(args.song_ids, args.dry_run, args.separate, args.limit, args.ledger))


if __name__ == "__main__":
    sys.exit(main())
