"""Catalog-wide backfill of timed lyrics (follow-along highlighting).

Re-transcribes songs through the same seam the API uses
(``src.api.lyrics_jobs.extract_and_store``) so the batch and the /produce
"Re-extract" button can never drift on which audio is transcribed or how the
result is stored. Each song gets isolated vocals where possible (a reused
``vocals`` stem, else an in-job Demucs pass), word timestamps, and a
``song_lyric_timings`` record.

This is a **long** run — minutes per song over ~1,300 songs — so it is built to
be interrupted and resumed:

  * **The database is the checkpoint.** A song is "done" when it has a
    ``song_lyric_timings`` row, so re-running simply skips finished work. There
    is no state file to keep in sync with reality.
  * **Failures are remembered** in a small JSON ledger so a permanently broken
    track (missing audio, no detectable vocals) isn't retried on every resume.
    ``--retry-failed`` clears that.
  * **Ctrl-C stops cleanly** after the current song, writing the ledger first.

The Whisper model is loaded **once** and reused for every track. Building an
extractor per song (what the per-request API path does, correctly, for a single
song) would spend tens of seconds per track loading models — hours across the
catalog, doing nothing.

Run it where the models and GPU are — inside the backend container:

    docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --status
    docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --dry-run
    docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --limit 5
    docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --yes

Useful flags:
    --status         Coverage report only; changes nothing.
    --dry-run        List the songs that would be processed, then exit.
    --limit N        Process at most N songs (start small to sanity-check output).
    --song-id ID     Process exactly one song (repeatable).
    --redo-all       Re-extract every song, including ones with current timings.
    --redo-stale     Also re-extract songs whose timings went stale after an edit.
    --retry-failed   Ignore the failure ledger and retry previously failed songs.
    --no-separate-vocals  Transcribe the full mix (faster, noticeably worse timing).
    --ledger PATH    Where to keep the failure ledger.
"""

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.api import lyrics_jobs
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill-lyric-timings")

# Quieten the per-song extractor chatter; the script prints its own progress.
logging.getLogger("lyrics-extractor").setLevel(logging.WARNING)

DEFAULT_LEDGER = project_root / "lyric_timing_backfill_failures.json"

# Set by the SIGINT handler so the loop finishes the current song and stops.
_stop_requested = False


def _request_stop(_signum, _frame) -> None:
    global _stop_requested
    if _stop_requested:
        # A second Ctrl-C means "stop now", not "stop politely".
        raise KeyboardInterrupt
    _stop_requested = True
    print("\n\n  Stop requested — finishing the current song, then exiting.")
    print("  (Ctrl-C again to abandon it immediately.)\n")


# --------------------------------------------------------------------------
# Failure ledger
# --------------------------------------------------------------------------

def load_ledger(path: Path) -> Dict[str, Any]:
    """Read the failure ledger, or an empty one if absent/corrupt."""
    if not path.exists():
        return {"failures": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("failures"), dict):
            return data
        logger.warning("Ledger at %s has an unexpected shape; starting fresh", path)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read ledger %s (%s); starting fresh", path, exc)
    return {"failures": {}}


def save_ledger(path: Path, ledger: Dict[str, Any]) -> None:
    """Persist the failure ledger. Never raises — losing it only costs retries."""
    try:
        ledger["updated_at"] = datetime.now().isoformat(timespec="seconds")
        path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write ledger %s: %s", path, exc)


# --------------------------------------------------------------------------
# Work selection
# --------------------------------------------------------------------------

def resolve_audio_path(song_id: int) -> Optional[Path]:
    """Locate a song's catalog audio file, mirroring the produce router's rule."""
    from src.api import radio_service

    matches = list(radio_service.AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    return matches[0] if matches else None


def select_songs(
    coverage: List[Dict[str, Any]],
    redo_all: bool,
    redo_stale: bool,
    song_ids: Optional[List[int]],
) -> List[Dict[str, Any]]:
    """Pick which songs this run should process, in catalog order."""
    if song_ids:
        wanted = set(song_ids)
        return [row for row in coverage if row["id"] in wanted]

    selected = []
    for row in coverage:
        if redo_all or not row["has_timings"]:
            selected.append(row)
        elif redo_stale and row["timing_status"] == "stale":
            selected.append(row)
    return selected


def summarize_coverage(coverage: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count songs by timed-lyric state."""
    summary = {
        "total": len(coverage),
        "current": 0,
        "stale": 0,
        "missing": 0,
        "from_vocals": 0,
        "from_mix": 0,
    }
    for row in coverage:
        if not row["has_timings"]:
            summary["missing"] += 1
            continue
        if row["timing_status"] == "stale":
            summary["stale"] += 1
        else:
            summary["current"] += 1
        if row["audio_source"] == lyrics_jobs.AUDIO_SOURCE_VOCALS:
            summary["from_vocals"] += 1
        else:
            summary["from_mix"] += 1
    return summary


def print_coverage(summary: Dict[str, int]) -> None:
    print("\nTimed-lyric coverage:")
    print(f"  Songs in catalog:      {summary['total']}")
    print(f"  With current timings:  {summary['current']}")
    print(f"    ...from isolated vocals: {summary['from_vocals']}")
    print(f"    ...from the full mix:    {summary['from_mix']}")
    print(f"  Stale (edited since):  {summary['stale']}")
    print(f"  No timings yet:        {summary['missing']}")


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def build_extractor(separate_vocals: bool):
    """Construct the one LyricsExtractor the whole run shares.

    Demucs is left unloaded: ``separate_vocals()`` lazy-loads it on the first
    song that actually needs separation, and songs with a reusable vocals stem
    never do. Once loaded it stays loaded for the rest of the run.
    """
    from src.rag.lyrics_extractor import LyricsExtractor

    extractor = LyricsExtractor(
        whisper_model_size=lyrics_jobs.WHISPER_MODEL,
        use_gpu=True,
        min_confidence=0.5,
        load_demucs=False,
    )
    if not extractor.is_available():
        raise RuntimeError(
            "Lyrics extractor unavailable — faster-whisper is not installed. "
            "Run this inside the bigflavor-backend container."
        )
    if separate_vocals:
        from src.rag.lyrics_extractor import DEMUCS_AVAILABLE

        if not DEMUCS_AVAILABLE:
            logger.warning(
                "Demucs is not installed — songs without an existing vocals stem "
                "will be transcribed from the full mix (worse timing accuracy)."
            )
    return extractor


async def backfill(
    limit: Optional[int] = None,
    song_ids: Optional[List[int]] = None,
    redo_all: bool = False,
    redo_stale: bool = False,
    retry_failed: bool = False,
    separate_vocals: bool = True,
    dry_run: bool = False,
    status_only: bool = False,
    skip_confirmation: bool = False,
    ledger_path: Path = DEFAULT_LEDGER,
) -> int:
    """Run the backfill. Returns a process exit code."""
    print("\n" + "=" * 70)
    print("Timed-Lyric Backfill")
    print("=" * 70)

    db = DatabaseManager()
    try:
        await db.connect()
    except Exception as exc:
        print(
            f"\nERROR: could not connect to PostgreSQL ({exc}).\n"
            "  Is the stack up? `docker-compose up -d postgres`\n"
        )
        return 2

    # CLAP is for audio-similarity search; lyric indexing only needs the text model.
    rag = SongRAGSystem(db, use_clap=False)

    try:
        # Storing lyrics re-embeds them. Without sentence-transformers, _embed_text
        # falls back to a zero vector per song — harmless for one song, but a
        # catalog-wide run would quietly flatten every lyric embedding and destroy
        # lyric search. Refuse rather than let that happen unnoticed.
        if not status_only and not dry_run:
            if getattr(rag, "text_embedding_model", None) is None:
                print(
                    "\nERROR: the text embedding model is unavailable "
                    "(sentence-transformers is not installed here).\n"
                    "  Lyrics would be stored with zero-vector embeddings, which "
                    "would break lyric search\n  for every song this run touches.\n\n"
                    "  Run it inside the backend container instead:\n"
                    "    docker exec -it bigflavor-backend python -m "
                    "scripts.backfill_lyric_timings --status\n"
                )
                return 2

        await db.ensure_song_lyric_timings_table()
        coverage = await db.list_lyric_timing_coverage()
        print_coverage(summarize_coverage(coverage))

        if status_only:
            return 0

        selected = select_songs(coverage, redo_all, redo_stale, song_ids)

        ledger = load_ledger(ledger_path)
        failures: Dict[str, Any] = {} if retry_failed else ledger["failures"]

        # Resolve audio up front: a song with no file on disk can never succeed,
        # so it belongs in the skipped column, not in the work queue.
        queue, missing_audio, previously_failed = [], [], []
        for row in selected:
            if str(row["id"]) in failures:
                previously_failed.append(row)
                continue
            audio_path = resolve_audio_path(row["id"])
            if audio_path is None:
                missing_audio.append(row)
                continue
            queue.append((row, audio_path))

        if missing_audio:
            print(f"\nSkipping {len(missing_audio)} songs with no audio file on disk.")
        if previously_failed:
            print(
                f"Skipping {len(previously_failed)} songs that failed a previous run "
                f"(--retry-failed to try again)."
            )

        if limit:
            queue = queue[:limit]

        if not queue:
            print("\nNothing to do — every selected song already has timings.")
            return 0

        print(f"\nTo process: {len(queue)} songs")
        print(f"  Vocal isolation: {'on' if separate_vocals else 'OFF (full mix)'}")
        print(f"  Whisper model:   {lyrics_jobs.WHISPER_MODEL}")
        print(f"  Ledger:          {ledger_path}")

        if dry_run:
            print("\n-- dry run: songs that would be processed --")
            for row, audio_path in queue[:50]:
                state = "stale" if row["timing_status"] == "stale" else (
                    "has timings" if row["has_timings"] else "no timings"
                )
                print(f"  {row['id']:>6}  {(row['title'] or '')[:48]:<50} ({state})")
            if len(queue) > 50:
                print(f"  ... and {len(queue) - 50} more")
            return 0

        if len(queue) > 10 and not skip_confirmation:
            print(
                "\nThis takes minutes per song. It is safe to interrupt (Ctrl-C) "
                "and re-run; finished songs are skipped."
            )
            if input(f"Process {len(queue)} songs? (y/n): ").strip().lower() != "y":
                print("Cancelled.")
                return 0

        print("\nLoading Whisper (once for the whole run)...")
        load_start = time.time()
        extractor = build_extractor(separate_vocals)
        print(f"Model ready in {_format_duration(time.time() - load_start)}.\n")

        signal.signal(signal.SIGINT, _request_stop)

        succeeded, failed, durations = 0, 0, []
        run_start = time.time()

        for index, (row, audio_path) in enumerate(queue, 1):
            if _stop_requested:
                break

            song_id = row["id"]
            title = (row["title"] or "")[:44]
            elapsed = time.time() - run_start
            eta = ""
            if durations:
                mean = sum(durations) / len(durations)
                eta = f"  ETA {_format_duration(mean * (len(queue) - index + 1))}"
            print(f"[{index}/{len(queue)}] {song_id:>6} {title:<46}{eta}", flush=True)

            song_start = time.time()
            try:
                summary = await lyrics_jobs.extract_and_store(
                    song_id,
                    str(audio_path),
                    rag,
                    db,
                    separate_vocals=separate_vocals,
                    extractor=extractor,
                )
                took = time.time() - song_start
                durations.append(took)
                succeeded += 1
                # A song that fell back to the mix isn't a failure, but it is worth
                # seeing in the log — its timings will be the least accurate.
                source_note = (
                    "vocals" if summary["audio_source"] == lyrics_jobs.AUDIO_SOURCE_VOCALS
                    else "MIX"
                )
                print(
                    f"         ok — {summary['line_count']} lines, "
                    f"{len(summary['lyrics'])} chars, {source_note}, "
                    f"{_format_duration(took)}"
                )
                # Clear any stale ledger entry now that this song has succeeded.
                ledger["failures"].pop(str(song_id), None)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                failed += 1
                reason = str(exc)
                print(f"         FAILED — {reason}")
                logger.debug("Extraction failed for song %s", song_id, exc_info=True)
                ledger["failures"][str(song_id)] = {
                    "title": row["title"],
                    "error": reason,
                    "failed_at": datetime.now().isoformat(timespec="seconds"),
                }
                save_ledger(ledger_path, ledger)

        save_ledger(ledger_path, ledger)

        print("\n" + "=" * 70)
        print("Summary")
        print("=" * 70)
        processed = succeeded + failed
        print(f"  Processed:  {processed} of {len(queue)} queued")
        print(f"  Succeeded:  {succeeded}")
        print(f"  Failed:     {failed}")
        print(f"  Wall clock: {_format_duration(time.time() - run_start)}")
        if durations:
            print(f"  Per song:   {_format_duration(sum(durations) / len(durations))} avg")
        if failed:
            print(f"\n  Failures recorded in {ledger_path}")
            print("  Re-run with --retry-failed once the cause is addressed.")
        if _stop_requested and processed < len(queue):
            print(f"\n  Stopped early — {len(queue) - processed} songs left.")
            print("  Re-run the same command to pick up where this left off.")

        print_coverage(summarize_coverage(await db.list_lyric_timing_coverage()))
        return 1 if failed and not succeeded else 0

    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill timed lyrics across the catalog (resumable)."
    )
    parser.add_argument("--status", action="store_true",
                        help="Print coverage and exit; changes nothing")
    parser.add_argument("--dry-run", action="store_true",
                        help="List the songs that would be processed, then exit")
    parser.add_argument("--limit", type=int,
                        help="Process at most N songs this run")
    parser.add_argument("--song-id", type=int, action="append", dest="song_ids",
                        help="Process exactly this song (repeatable)")
    parser.add_argument("--redo-all", action="store_true",
                        help="Re-extract every song, including ones already done")
    parser.add_argument("--redo-stale", action="store_true",
                        help="Also re-extract songs whose timings went stale")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Ignore the failure ledger and retry failed songs")
    parser.add_argument("--no-separate-vocals", action="store_true",
                        help="Transcribe the full mix (faster, worse timing accuracy)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the confirmation prompt")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER,
                        help=f"Failure ledger path (default: {DEFAULT_LEDGER.name})")

    args = parser.parse_args()

    try:
        return asyncio.run(backfill(
            limit=args.limit,
            song_ids=args.song_ids,
            redo_all=args.redo_all,
            redo_stale=args.redo_stale,
            retry_failed=args.retry_failed,
            separate_vocals=not args.no_separate_vocals,
            dry_run=args.dry_run,
            status_only=args.status,
            skip_confirmation=args.yes,
            ledger_path=args.ledger,
        ))
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        # Release GPU memory before exit, matching index_lyrics.py.
        try:
            import gc

            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
        except Exception:
            pass
