"""Give every playable audio file a catalog row (issue #107).

`audio_library/` held 1,415 top-level `{song_id}_*.mp3` files but `songs` held
1,341 rows, so 74 playable songs had no catalog row at all. Anything without a
row is invisible to search, the DJ, lyrics and embeddings — the radio's own
directory scan was the only way those files could ever reach a listener.

Cause: comparing the cached scrapes, `scraper/scraped_songs_20251106_173012.json`
describes 60 of the 74, while the 2025-11-10 scrape the catalog was loaded from
describes none of them. They were dropped between the two scrapes and their audio
files stayed behind. So the best available metadata for most of them is the older
scrape; the rest are named from the file itself.

Title precedence, best source first:
  1. the older scrape's title (60 of 74) — also carries session, recorded_on,
     audio_url and instruments, inserted through the same path the scraper uses
  2. the file's own ID3 title, read with ffprobe (no mutagen in the image)
  3. the filename with the `{song_id}_` prefix stripped

This only makes the rows *exist*. Fields derived from audio (duration, tempo,
key, energy, mood, genre) and the embeddings are filled by the existing
back-fills, which select on NULLs and therefore pick these songs up:
    python -m src.rag.backfill_audio_metadata
    python scripts/backfill_song_tags.py
    python scripts/backfill_metadata_embeddings.py

Idempotent: a song that already has a row is skipped, so re-running after new
files land only inserts what is missing.

Usage (inside the backend container, which mounts audio_library):
    docker exec bigflavor-backend python scripts/backfill_orphan_songs.py --status
    docker exec bigflavor-backend python scripts/backfill_orphan_songs.py --dry-run
    docker exec bigflavor-backend python scripts/backfill_orphan_songs.py

`scraper/` is not mounted into the container, so pass the scrape data explicitly
when running there (copy it in first with `docker cp`):
    --scrape-dir /tmp/scrape
"""
import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager  # noqa: E402
from scraper.scraped_data_manager import ScrapedDataManager  # noqa: E402

AUDIO_LIBRARY_DIR = REPO_ROOT / "audio_library"
DEFAULT_SCRAPE_DIR = REPO_ROOT / "scraper"

# Only top-level catalog files are songs. audio_library/ also holds produced/
# and sessions/ subtrees whose filenames carry no catalog id.
CATALOG_FILE_RE = re.compile(r"^(\d+)_.*\.mp3$", re.IGNORECASE)

# The site's numeric song id appears in the scraped audio_url as /audio/<id>/.
AUDIO_URL_ID_RE = re.compile(r"/audio/(\d+)/")

FFPROBE_TIMEOUT_SECONDS = 15


def song_id_from_name(name: str) -> Optional[int]:
    """The leading id of a top-level catalog filename, or None."""
    match = CATALOG_FILE_RE.match(name)
    return int(match.group(1)) if match else None


def catalog_files(names: Iterable[str]) -> Dict[int, str]:
    """Map song id -> filename for top-level catalog files.

    First filename wins, so the result is stable regardless of listing order
    when two files somehow share an id.
    """
    found: Dict[int, str] = {}
    for name in sorted(names):
        song_id = song_id_from_name(name)
        if song_id is not None:
            found.setdefault(song_id, name)
    return found


def title_from_filename(name: str) -> str:
    """"890_KWE_Lull_Me_Away.mp3" -> "KWE Lull Me Away"."""
    stem = Path(name).stem
    stem = re.sub(r"^\d+_", "", stem)
    return re.sub(r"\s+", " ", stem.replace("_", " ")).strip()


def scraped_record_id(record: Dict[str, Any]) -> Optional[int]:
    """The numeric song id of a scraped record.

    Older scrapes key records by slug and carry the numeric id only inside
    audio_url; newer ones use a numeric id directly.
    """
    raw = record.get("id")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    match = AUDIO_URL_ID_RE.search(str(record.get("audio_url", "")))
    return int(match.group(1)) if match else None


def usable_scrape_record(record: Dict[str, Any]) -> bool:
    """A record worth taking metadata from: named, and not a skip marker."""
    return bool(record.get("title")) and not record.get("skipped")


def build_scrape_index(scrape_dir: Path) -> Dict[int, Dict[str, Any]]:
    """Index every cached scrape by numeric song id, oldest file first.

    Files are read in sorted (chronological) order and the first usable record
    for an id wins, which is deliberate: the 2025-11-06 scrape is the only one
    that still describes the orphaned songs, and a later scrape that dropped
    them must not shadow it.
    """
    index: Dict[int, Dict[str, Any]] = {}
    for path in sorted(scrape_dir.glob("scraped_songs_*.json")):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"  skipping unreadable scrape {path.name}: {exc}")
            continue
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict) or not usable_scrape_record(record):
                continue
            song_id = scraped_record_id(record)
            if song_id is not None:
                index.setdefault(song_id, record)
    return index


def id3_title(path: Path) -> Optional[str]:
    """The file's ID3 title via ffprobe, or None if it has none.

    ffprobe rather than a tag library because the backend image ships ffmpeg but
    no mutagen, and adding a dependency would mean rebuilding the image.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format_tags=title",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"  ffprobe failed for {path.name}: {exc}")
        return None
    title = result.stdout.strip()
    return title or None


def build_song_data(
    song_id: int,
    filename: str,
    scraped: Optional[Dict[str, Any]],
    tag_title: Optional[str],
) -> Tuple[Dict[str, Any], str]:
    """Build the insert payload for one orphan, plus which source named it."""
    if scraped is not None:
        song_data: Dict[str, Any] = {
            "id": song_id,
            "title": scraped["title"],
            "session": scraped.get("session"),
            "recorded_on": scraped.get("recorded_on"),
            "audio_url": scraped.get("audio_url"),
            "instruments": scraped.get("instruments") or [],
        }
        return song_data, "scrape"

    if tag_title:
        return {"id": song_id, "title": tag_title}, "id3"

    return {"id": song_id, "title": title_from_filename(filename)}, "filename"


async def fetch_catalog_ids(db: DatabaseManager) -> set:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM songs")
    return {row["id"] for row in rows}


def find_orphans(audio_dir: Path, catalog_ids: set) -> Dict[int, str]:
    """Top-level catalog files whose id has no songs row."""
    names = [p.name for p in audio_dir.iterdir() if p.is_file()]
    return {
        song_id: name
        for song_id, name in catalog_files(names).items()
        if song_id not in catalog_ids
    }


async def run(
    audio_dir: Path,
    scrape_dir: Path,
    limit: Optional[int],
    dry_run: bool,
    status_only: bool,
) -> int:
    db = DatabaseManager()
    await db.connect()
    try:
        catalog_ids = await fetch_catalog_ids(db)
        orphans = find_orphans(audio_dir, catalog_ids)
        total_files = len(catalog_files([p.name for p in audio_dir.iterdir() if p.is_file()]))

        print(f"Top-level catalog files: {total_files}")
        print(f"Rows in songs:           {len(catalog_ids)}")
        print(f"Files with no row:       {len(orphans)}")
        missing_files = len(catalog_ids - set(catalog_files(
            [p.name for p in audio_dir.iterdir() if p.is_file()]
        )))
        print(f"Rows with no file:       {missing_files}")

        if status_only or not orphans:
            return 0

        scrape_index = build_scrape_index(scrape_dir)
        print(f"Scraped records indexed: {len(scrape_index)}")

        targets = sorted(orphans.items())
        if limit:
            targets = targets[:limit]

        manager = ScrapedDataManager(db)
        counts = {"scrape": 0, "id3": 0, "filename": 0}
        inserted = 0

        for song_id, filename in targets:
            scraped = scrape_index.get(song_id)
            tag_title = None
            if scraped is None:
                tag_title = id3_title(audio_dir / filename)
            song_data, source = build_song_data(song_id, filename, scraped, tag_title)
            counts[source] += 1

            print(f"  {song_id:>5}  [{source:8}] {song_data['title'][:60]}")
            if dry_run:
                continue
            await manager.insert_song_with_details(song_data)
            inserted += 1

        print()
        print(f"Named from scrape: {counts['scrape']}, from ID3: {counts['id3']}, "
              f"from filename: {counts['filename']}")
        if dry_run:
            print(f"Dry run — nothing written ({len(targets)} would be inserted).")
        else:
            print(f"Inserted {inserted} song rows.")
            remaining = await fetch_catalog_ids(db)
            print(f"Files with no row now: {len(find_orphans(audio_dir, remaining))}")
        return 0
    finally:
        await db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Insert a catalog row for every playable audio file that lacks one (issue #107)."
    )
    parser.add_argument("--status", action="store_true", help="Show the counts and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted.")
    parser.add_argument("--limit", type=int, help="Process at most N orphans.")
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=AUDIO_LIBRARY_DIR,
        help=f"Audio library directory (default: {AUDIO_LIBRARY_DIR}).",
    )
    parser.add_argument(
        "--scrape-dir",
        type=Path,
        default=DEFAULT_SCRAPE_DIR,
        help=f"Directory of scraped_songs_*.json (default: {DEFAULT_SCRAPE_DIR}).",
    )
    args = parser.parse_args()

    if not args.audio_dir.is_dir():
        sys.exit(f"Audio library not found: {args.audio_dir}")
    if not args.status and not args.scrape_dir.is_dir():
        print(f"Warning: no scrape directory at {args.scrape_dir} — "
              "falling back to ID3/filename titles for every song.")

    sys.exit(await run(
        audio_dir=args.audio_dir,
        scrape_dir=args.scrape_dir,
        limit=args.limit,
        dry_run=args.dry_run,
        status_only=args.status,
    ))


if __name__ == "__main__":
    asyncio.run(main())
