"""
Back-fill songs.duration_seconds and songs.tempo_bpm from audio (issue #52).

bigflavorband.com never provided duration or tempo, so these columns are null
for most songs even though the audio is reliably analyzable. This batch job
computes both from the catalog audio file we already have (librosa, via
AudioEmbeddingExtractor.extract_all_features) and writes them back to the songs
table — only for songs where the value is currently null, so re-runs process
only missing data (the "incremental" convention, like derive_energy_mood).

A song whose audio file is missing or unreadable is skipped and logged, never
errored. duration_seconds is an INTEGER column, so the float duration is rounded.

Usage (inside the backend container, where the audio_library volume is mounted):
    docker exec bigflavor-backend python -m src.rag.backfill_audio_metadata --status
    docker exec bigflavor-backend python -m src.rag.backfill_audio_metadata --limit 5 --dry-run
    docker exec bigflavor-backend python -m src.rag.backfill_audio_metadata            # all missing
    docker exec bigflavor-backend python -m src.rag.backfill_audio_metadata --reindex  # redo all
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.rag.audio_embedding_extractor import AudioEmbeddingExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("backfill-audio-metadata")

# Catalog audio lives here; files are named "{song_id}_*.mp3" (same convention
# the radio/produce paths resolve by).
AUDIO_LIBRARY_DIR = project_root / "audio_library"


def resolve_audio_path(song_id: int) -> Optional[Path]:
    """Locate the catalog audio file for a song, or None if absent.

    Resolves by the "{song_id}_*.mp3" glob used everywhere else, rather than
    re-deriving the sanitized title, so a renamed song still matches.
    """
    matches = sorted(AUDIO_LIBRARY_DIR.glob(f"{song_id}_*.mp3"))
    return matches[0] if matches else None


def derive_audio_metadata(features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map AudioEmbeddingExtractor.extract_all_features output to song columns.

    Returns {duration_seconds: int, tempo_bpm: float} or None if the librosa
    features are empty/unusable (extract returns {} on failure). duration_seconds
    is an INTEGER column, so the float duration is rounded.
    """
    librosa_features = features.get("librosa_features") or {}
    duration = librosa_features.get("duration")
    tempo = librosa_features.get("tempo")
    if duration is None and tempo is None:
        return None
    return {
        "duration_seconds": round(float(duration)) if duration is not None else None,
        "tempo_bpm": float(tempo) if tempo is not None else None,
    }


async def fetch_songs(
    db: DatabaseManager, reindex: bool, limit: Optional[int]
) -> List[Dict[str, Any]]:
    """Fetch songs needing duration or tempo back-filled."""
    where = "" if reindex else "WHERE (s.duration_seconds IS NULL OR s.tempo_bpm IS NULL)"
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    query = f"""
        SELECT s.id, s.title, s.duration_seconds, s.tempo_bpm
        FROM songs s
        {where}
        ORDER BY s.id
        {limit_sql}
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) for r in rows]


async def status(db: DatabaseManager) -> None:
    query = """
        SELECT COUNT(*) AS total,
               COUNT(duration_seconds) AS duration_filled,
               COUNT(tempo_bpm) AS tempo_filled
        FROM songs
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query)
    print("\nAudio-metadata status:")
    print(f"  Total songs       : {row['total']}")
    print(f"  duration_seconds  : {row['duration_filled']}")
    print(f"  tempo_bpm         : {row['tempo_filled']}")


async def backfill(
    limit: Optional[int], reindex: bool, dry_run: bool
) -> None:
    db = DatabaseManager()
    await db.connect()
    # CLAP is not needed here — we only read librosa duration/tempo — so skip it
    # to keep the job light and avoid loading the model.
    extractor = AudioEmbeddingExtractor(use_clap=False)

    try:
        songs = await fetch_songs(db, reindex=reindex, limit=limit)
        total = len(songs)
        print("\n" + "=" * 70)
        print(f"Back-fill audio metadata   ({'DRY RUN' if dry_run else 'APPLY'})")
        print("=" * 70)
        print(f"Songs to process: {total}")
        if not total:
            print("Nothing to do.")
            return

        # COALESCE so a value already present (e.g. only one of the two was null)
        # is never overwritten — re-runs only fill missing data.
        update_sql = """
            UPDATE songs
            SET duration_seconds = COALESCE(duration_seconds, $2),
                tempo_bpm = COALESCE(tempo_bpm, $3),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """

        succeeded = 0
        skipped = 0
        failed = 0
        for i, song in enumerate(songs, 1):
            song_id = song["id"]
            audio_path = resolve_audio_path(song_id)
            if audio_path is None:
                skipped += 1
                logger.warning(f"Song {song_id} ({song['title']}): no audio file — skipping")
                continue

            try:
                # librosa work is CPU-bound; keep it off the event loop.
                features = await asyncio.to_thread(
                    extractor.extract_all_features, str(audio_path)
                )
                derived = derive_audio_metadata(features)
                if derived is None:
                    failed += 1
                    logger.warning(f"Song {song_id} ({song['title']}): no usable features")
                    continue

                if not dry_run:
                    async with db.pool.acquire() as conn:
                        await conn.execute(
                            update_sql, song_id,
                            derived["duration_seconds"], derived["tempo_bpm"],
                        )

                succeeded += 1
                if dry_run or i <= 10 or i % 50 == 0:
                    print(
                        f"  [{i}/{total}] {song['title'][:40]:40s} -> "
                        f"{derived['duration_seconds']}s, "
                        f"{round(derived['tempo_bpm']) if derived['tempo_bpm'] else '?'} BPM"
                    )
            except Exception as e:
                failed += 1
                logger.error(f"Song {song_id} ({song['title']}): {e}")

        print("\n" + "-" * 70)
        print(f"Filled: {succeeded}   No audio: {skipped}   Failed: {failed}")
        if dry_run:
            print("DRY RUN -- no changes written. Re-run without --dry-run to commit.")
        else:
            print("[OK] audio metadata written.")
            await status(db)
    finally:
        await db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back-fill songs.duration_seconds and songs.tempo_bpm from audio."
    )
    parser.add_argument("--status", action="store_true", help="Show fill status and exit.")
    parser.add_argument("--limit", type=int, help="Process at most N songs.")
    parser.add_argument(
        "--reindex", action="store_true", help="Reprocess all songs, not just missing ones."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Analyze and print without writing."
    )
    args = parser.parse_args()

    if args.status:
        db = DatabaseManager()
        await db.connect()
        try:
            await status(db)
        finally:
            await db.close()
        return

    await backfill(limit=args.limit, reindex=args.reindex, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
