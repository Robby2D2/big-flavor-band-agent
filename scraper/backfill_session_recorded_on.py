"""
Back-fill songs.session and songs.recorded_on from scraped JSON.

These two fields were captured during scraping but never written to the songs
table: insert_song() (database/database.py) omits both columns, so the data
was dropped on load. This one-off script reads the latest scraped_songs_*.json
backup and back-fills the columns by song id.

Safe by default: runs as a dry run unless --apply is passed, and uses COALESCE
so an existing (non-null) value is never overwritten with a scraped one.

Usage:
    python -m scraper.backfill_session_recorded_on            # dry run
    python -m scraper.backfill_session_recorded_on --apply     # write changes
    python -m scraper.backfill_session_recorded_on --json scraper/scraped_songs_X.json
"""

import argparse
import asyncio
import glob
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import json

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill-session-recorded-on")


def find_latest_json() -> Optional[Path]:
    """Return the most recent scraped_songs_*.json backup, or None."""
    matches = sorted(glob.glob(str(project_root / "scraper" / "scraped_songs_*.json")))
    return Path(matches[-1]) if matches else None


def parse_recorded_on(value: str) -> Optional[date]:
    """Parse a scraped 'M/D/YY' string into a date (20YY). Returns None if unparseable."""
    parts = value.strip().split("/")
    if len(parts) != 3:
        logger.warning(f"Unexpected recorded_on format, skipping: {value!r}")
        return None
    try:
        month, day, yy = (int(p) for p in parts)
    except ValueError:
        logger.warning(f"Non-numeric recorded_on, skipping: {value!r}")
        return None
    try:
        return date(2000 + yy, month, day)
    except ValueError:
        logger.warning(f"Invalid calendar date, skipping: {value!r}")
        return None


async def backfill(json_path: Path, apply: bool) -> None:
    raw = json.loads(json_path.read_text(encoding="utf-8"))

    # Build (id, session, recorded_on) records for entries that carry either field.
    records = []
    for entry in raw:
        song_id = entry.get("id")
        if not isinstance(song_id, int):
            continue
        session = entry.get("session") or None
        recorded_on_raw = entry.get("recorded_on")
        recorded_on = parse_recorded_on(recorded_on_raw) if recorded_on_raw else None
        if session is None and recorded_on is None:
            continue
        records.append((song_id, session, recorded_on))

    print("\n" + "=" * 70)
    print(f"Back-fill session / recorded_on   ({'APPLY' if apply else 'DRY RUN'})")
    print("=" * 70)
    print(f"\nSource: {json_path.name}")
    print(f"Records with session or recorded_on: {len(records)}")
    print(f"  with session     : {sum(1 for _, s, _ in records if s)}")
    print(f"  with recorded_on : {sum(1 for _, _, r in records if r)}")

    db = DatabaseManager()
    await db.connect()
    try:
        # COALESCE preserves any value already present; only fills NULLs.
        query = """
            UPDATE songs
            SET session = COALESCE(session, $2::varchar),
                recorded_on = COALESCE(recorded_on, $3::date),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
              AND (
                  ($2::varchar IS NOT NULL AND session IS NULL)
                  OR ($3::date IS NOT NULL AND recorded_on IS NULL)
              )
        """

        updated = 0
        missing = []
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                for song_id, session, recorded_on in records:
                    exists = await conn.fetchval(
                        "SELECT 1 FROM songs WHERE id = $1", song_id
                    )
                    if not exists:
                        missing.append(song_id)
                        continue
                    status = await conn.execute(query, song_id, session, recorded_on)
                    # status looks like "UPDATE 1" / "UPDATE 0"
                    if status.endswith("1"):
                        updated += 1

                if not apply:
                    raise _Rollback()

        print(f"\nSongs updated: {updated}")
        if missing:
            print(f"Scraped ids not found in DB (skipped): {len(missing)}")
            print(f"  e.g. {missing[:10]}")
        if apply:
            print("\n[OK] Changes committed.")
        else:
            print("\nDRY RUN -- no changes written. Re-run with --apply to commit.")
    except _Rollback:
        print(f"\nSongs that would be updated: {updated}")
        if missing:
            print(f"Scraped ids not found in DB (would skip): {len(missing)}")
            print(f"  e.g. {missing[:10]}")
        print("\nDRY RUN -- no changes written. Re-run with --apply to commit.")
    finally:
        await db.close()


class _Rollback(Exception):
    """Sentinel to abort the transaction in dry-run mode."""


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back-fill songs.session and songs.recorded_on from scraped JSON."
    )
    parser.add_argument(
        "--json", help="Path to scraped_songs_*.json (default: most recent in scraper/)."
    )
    parser.add_argument(
        "--apply", action="store_true", help="Write changes (default is a dry run)."
    )
    args = parser.parse_args()

    json_path = Path(args.json) if args.json else find_latest_json()
    if not json_path or not json_path.exists():
        print("❌ No scraped_songs_*.json found. Pass one with --json.")
        sys.exit(1)

    await backfill(json_path, apply=args.apply)


if __name__ == "__main__":
    asyncio.run(main())
