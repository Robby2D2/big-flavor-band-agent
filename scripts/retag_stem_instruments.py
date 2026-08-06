"""Catalog-wide re-tag of stem instruments (and, mainly, the ``silent`` verdict).

Runs every stem back through the same seam the API uses
(``instrument_tagging.identify_instruments`` -> ``db.set_stem_instrument_tags``,
exactly what ``POST /api/produce/stems/{id}/identify`` does), so the batch and
the per-stem retry button can never drift on how a stem is judged or stored.

**Why this exists.** The console hides stems tagged ``silent``, and silence used
to be judged on per-window RMS against a -80 dBFS floor. An empty Demucs stem
isn't digital silence, it's low-level bleed — measured at ~-61 dBFS RMS, ~9x
over that gate — so empty stems were scored as present-but-unrecognised and kept
showing up. Silence is now judged on peak (see ``SILENCE_PEAK``). Tags already
written to the database keep the old verdict until something re-runs the tagger,
which is what this does.

Unlike the timed-lyric backfill there is no ledger or resume logic: tagging is
seconds per stem, the whole catalog is a short run, and re-running is harmless
(it simply overwrites each verdict with a freshly computed one). The database is
still the only state.

The tagger model is loaded **once** and reused for every stem — it is cached
module-level in ``instrument_tagging``, so a plain loop already gets this. The
per-request API path correctly builds nothing extra per call; here that means a
single model load for the entire run.

Run it where the models and GPU are — inside the backend container:

    docker exec -it bigflavor-backend python -m scripts.retag_stem_instruments --status
    docker exec -it bigflavor-backend python -m scripts.retag_stem_instruments --dry-run
    docker exec -it bigflavor-backend python -m scripts.retag_stem_instruments --yes

Useful flags:
    --status       Report current tagging/silent coverage only; changes nothing.
    --dry-run      List the stems that would be re-tagged, then exit.
    --limit N      Re-tag at most N stems (start small to sanity-check output).
    --song-id ID   Re-tag only this song's stems (repeatable).
    --untagged     Only stems never tagged, instead of re-tagging everything.
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.production import instrument_tagging

logging.basicConfig(level=logging.WARNING, format="%(message)s")


async def _collect_stems(
    db: DatabaseManager, song_ids: Optional[List[int]]
) -> List[Dict[str, Any]]:
    """Every stem of every *complete* set, newest set first.

    Failed sets are skipped: they have no stems on disk, so there is nothing to
    tag.
    """
    query = """
        SELECT s.id, s.name, s.path, s.stem_set_id, s.tagged_at,
               s.instrument_tags, ss.song_id
        FROM song_stems s
        JOIN song_stem_sets ss ON ss.id = s.stem_set_id
        WHERE ss.status = 'complete'
        ORDER BY ss.song_id, s.stem_set_id DESC, s.name
    """
    async with db.pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(query)]
    if song_ids:
        wanted = set(song_ids)
        rows = [r for r in rows if r["song_id"] in wanted]
    return rows


def _verdict(row: Dict[str, Any]) -> str:
    """How a stem currently reads to the console."""
    import json

    tags = row.get("instrument_tags")
    if isinstance(tags, str):  # asyncpg returns JSONB as text
        tags = json.loads(tags)
    if row.get("tagged_at") is None:
        return "untagged"
    return instrument_tagging.summarize_for_display(tags)


async def retag(
    limit: Optional[int] = None,
    song_ids: Optional[List[int]] = None,
    untagged_only: bool = False,
    dry_run: bool = False,
    status_only: bool = False,
    skip_confirmation: bool = False,
) -> int:
    print("\n" + "=" * 70)
    print("Stem Instrument Re-tag")
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

    try:
        stems = await _collect_stems(db, song_ids)
        if not stems:
            print("\nNo stems in any complete stem set — nothing to do.\n")
            return 0

        silent = sum(1 for s in stems if _verdict(s) == "silent")
        untagged = sum(1 for s in stems if _verdict(s) == "untagged")
        songs = len({s["song_id"] for s in stems})
        print(f"\n{len(stems)} stems across {songs} song(s) in complete sets")
        print(f"  currently marked silent : {silent}")
        print(f"  never tagged            : {untagged}")

        if status_only:
            print()
            for s in stems:
                print(f"  song {s['song_id']:>5}  {s['name']:<8} {_verdict(s)}")
            print()
            return 0

        targets = [s for s in stems if _verdict(s) == "untagged"] if untagged_only else stems
        if limit:
            targets = targets[:limit]
        if not targets:
            print("\nNothing matches those filters — nothing to do.\n")
            return 0

        print(f"\nWould re-tag {len(targets)} stem(s):")
        for s in targets:
            print(f"  song {s['song_id']:>5}  {s['name']:<8} (currently: {_verdict(s)})")

        if dry_run:
            print("\nDry run — nothing written.\n")
            return 0

        if not skip_confirmation:
            reply = input("\nProceed? [y/N] ").strip().lower()
            if reply not in ("y", "yes"):
                print("Aborted.")
                return 130

        print()
        changed = 0
        failed = 0
        for index, stem in enumerate(targets, start=1):
            before = _verdict(stem)
            label = f"[{index}/{len(targets)}] song {stem['song_id']} {stem['name']}"
            if not Path(stem["path"]).exists():
                print(f"{label}: SKIPPED — audio file missing ({stem['path']})")
                failed += 1
                continue
            try:
                # Blocking/CPU-bound, but this script owns the process — there is
                # no event loop serving requests to keep responsive.
                tags = instrument_tagging.identify_instruments(stem["path"])
                await db.set_stem_instrument_tags(stem["id"], tags)
            except Exception as exc:
                print(f"{label}: FAILED — {exc}")
                failed += 1
                continue

            after = instrument_tagging.summarize_for_display(tags)
            if after != before:
                changed += 1
                print(f"{label}: {before}  ->  {after}")
            else:
                print(f"{label}: {after} (unchanged)")

        now_silent = sum(
            1
            for s in await _collect_stems(db, song_ids)
            if _verdict(s) == "silent"
        )
        print("\n" + "-" * 70)
        print(f"Re-tagged {len(targets) - failed} stem(s); {changed} verdict(s) changed.")
        if failed:
            print(f"{failed} stem(s) could not be tagged (see above).")
        print(f"Stems now hidden from the console as silent: {now_silent}")
        print()
        return 1 if failed else 0
    finally:
        await db.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-tag stem instruments and refresh the silent verdict."
    )
    parser.add_argument("--status", action="store_true",
                        help="Report current coverage only; changes nothing")
    parser.add_argument("--dry-run", action="store_true",
                        help="List the stems that would be re-tagged, then exit")
    parser.add_argument("--limit", type=int,
                        help="Re-tag at most N stems")
    parser.add_argument("--song-id", type=int, action="append", dest="song_ids",
                        help="Re-tag only this song's stems (repeatable)")
    parser.add_argument("--untagged", action="store_true",
                        help="Only stems never tagged, instead of re-tagging everything")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip the confirmation prompt")

    args = parser.parse_args()

    try:
        return asyncio.run(retag(
            limit=args.limit,
            song_ids=args.song_ids,
            untagged_only=args.untagged,
            dry_run=args.dry_run,
            status_only=args.status,
            skip_confirmation=args.yes,
        ))
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
