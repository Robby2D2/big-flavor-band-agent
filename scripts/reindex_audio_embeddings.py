"""Rebuild every song's audio index in one pass, with CLAP (issue #111).

CLAP has never worked here: `clap_processor(audios=...)` raised on a kwarg
transformers had renamed, `extract_clap_embedding` caught it and returned None,
and `index_audio_file` stored the row anyway -- so all 1,415 rows in
`audio_embeddings` held a librosa-only `combined_embedding` and a NULL
`clap_embedding`, from the day indexing first ran.

Fixing the extractor is not enough on its own. CLAP and librosa-fallback vectors
would then share one column, and cosine distance between two different embedding
spaces is meaningless (CAT-05, CAT-11) -- a half-re-indexed catalog ranks worse
than a uniformly degraded one. So this is a *single-pass rebuild of every row*,
not a fill of the NULL ones, and it is a deliberate one-off: the incremental
"process only what is missing" path (CAT-08) is untouched and is still how new
songs are indexed.

**Resumable by construction.** The database is the checkpoint -- a row with both
a clap_embedding and a combined_embedding is done -- so an interrupted run is
re-run with the same command and picks up what is left. Nothing here is
destructive: migration 19 cleared combined_embedding once, and every write after
that only replaces a row's own vectors.

**It updates rows, it never inserts them.** `audio_embeddings` is unique on
`audio_path`, and 1,341 rows still carry a stale Windows-relative path that
cannot be opened in the container, while the 74 rows back-filled for issue #107
carry `/app/audio_library/...`. Indexing those through the upsert on a freshly
resolved path would create a *second* row per song and return each one twice from
search (CAT-04, CAT-07), so each row's audio_path is normalised first.

The CLAP weights load once and are reused for every file; loading them per song
would add hours to a job that is already 1,415 files long.

Usage (inside the backend container, which has the audio_library mount and CUDA):
    docker exec bigflavor-backend python scripts/reindex_audio_embeddings.py --status
    docker exec bigflavor-backend python scripts/reindex_audio_embeddings.py --limit 5
    docker exec bigflavor-backend python scripts/reindex_audio_embeddings.py
    docker exec bigflavor-backend python scripts/reindex_audio_embeddings.py --check
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager
from src.rag.backfill_audio_metadata import AUDIO_LIBRARY_DIR, resolve_audio_path
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("reindex-audio")

# The width of a complete representation: 37 librosa dimensions + CLAP's 512.
COMPLETE_DIMS = 549

STATUS_SQL = """
    SELECT COUNT(*)              AS rows_total,
           COUNT(clap_embedding) AS with_clap,
           COUNT(combined_embedding) AS with_combined,
           COUNT(*) FILTER (
               WHERE (clap_embedding IS NULL) <> (combined_embedding IS NULL)
           ) AS partial,
           COUNT(DISTINCT song_id) AS songs_covered
    FROM audio_embeddings
"""


async def read_status(db: DatabaseManager) -> Dict[str, Any]:
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(STATUS_SQL)
        dims = await conn.fetch(
            """
            SELECT vector_dims(combined_embedding) AS dims, COUNT(*) AS n
            FROM audio_embeddings
            WHERE combined_embedding IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """
        )
        songs_total = await conn.fetchval("SELECT COUNT(*) FROM songs")
    status = dict(row)
    status["songs_total"] = songs_total
    status["dimensions"] = {r["dims"]: r["n"] for r in dims}
    return status


def print_status(status: Dict[str, Any], heading: str) -> None:
    print(f"\n{heading}")
    print(f"  audio index rows      : {status['rows_total']}")
    print(f"  with clap_embedding   : {status['with_clap']}")
    print(f"  with combined         : {status['with_combined']}")
    print(f"  partial (one half)    : {status['partial']}")
    print(f"  songs covered / total : {status['songs_covered']} / {status['songs_total']}")
    print(f"  combined dimensions   : {status['dimensions'] or '(none stored)'}")


def check_complete(status: Dict[str, Any]) -> bool:
    """Is every audio index row a complete representation, all the same width?

    The post-run gate the spec asks for: a song counted as indexed must carry its
    whole searchable representation rather than half of it (CAT-12), and every row
    must be the same width so the catalog is compared inside one space (CAT-11).
    """
    problems: List[str] = []
    if status["partial"]:
        problems.append(
            f"{status['partial']} row(s) have one embedding half without the other"
        )
    if status["with_clap"] != status["rows_total"]:
        problems.append(
            f"{status['rows_total'] - status['with_clap']} row(s) have no clap_embedding"
        )
    if status["with_combined"] != status["rows_total"]:
        problems.append(
            f"{status['rows_total'] - status['with_combined']} row(s) have no combined_embedding"
        )
    stored_dims = sorted(status["dimensions"])
    if stored_dims and stored_dims != [COMPLETE_DIMS]:
        problems.append(f"combined_embedding widths are mixed: {stored_dims}")
    if status["songs_covered"] != status["songs_total"]:
        problems.append(
            f"{status['songs_total'] - status['songs_covered']} song(s) have no audio index row"
        )

    if problems:
        print("\nPartial audio index FOUND:")
        for problem in problems:
            print(f"  - {problem}")
        return False
    print(
        "\nNo song has a partial audio index: every row carries CLAP + combined at "
        f"{COMPLETE_DIMS} dimensions."
    )
    return True


async def fetch_pending(db: DatabaseManager, limit: Optional[int]) -> List[Dict[str, Any]]:
    """Rows whose audio index is not yet a complete CLAP representation.

    Ordered by id so a resumed run walks the catalog in the same order and the
    progress log means the same thing across runs.
    """
    query = """
        SELECT ae.id, ae.song_id, ae.audio_path, s.title
        FROM audio_embeddings ae
        LEFT JOIN songs s ON s.id = ae.song_id
        WHERE ae.clap_embedding IS NULL OR ae.combined_embedding IS NULL
        ORDER BY ae.id
    """
    args: List[Any] = []
    if limit is not None:
        query += " LIMIT $1"
        args.append(limit)
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query, *args)
    return [dict(r) for r in rows]


def readable_path(row: Dict[str, Any]) -> Optional[Path]:
    """Find the audio file a row is about, whatever shape its stored path is.

    The stored path is trusted only if it opens: 1,341 rows hold a Windows
    relative path written from the host, which is not a filename in the
    container. Falls back to the basename inside the audio library, then to the
    `{song_id}_*.mp3` glob every other path in this project resolves by.
    """
    stored = row["audio_path"]
    if stored:
        if Path(stored).is_file():
            return Path(stored)
        # A backslash is a legal character in a POSIX filename, so Path() will not
        # split a Windows path here -- take the basename by hand.
        basename = stored.replace("\\", "/").rsplit("/", 1)[-1]
        by_name = AUDIO_LIBRARY_DIR / basename
        if by_name.is_file():
            return by_name
    return resolve_audio_path(row["song_id"])


async def reindex(limit: Optional[int]) -> int:
    db = DatabaseManager()
    await db.connect()
    # use_clap=True is the whole point of this job: the extractor loads the CLAP
    # weights once here, and every file below reuses them.
    rag = SongRAGSystem(db, use_clap=True)

    try:
        if not rag.embedding_extractor.use_clap:
            logger.error(
                "CLAP is not available in this environment, so no complete audio "
                "index can be produced. Refusing to run -- a librosa-only pass is "
                "exactly what this job exists to replace."
            )
            return 1

        before = await read_status(db)
        print_status(before, "Before:")

        pending = await fetch_pending(db, limit)
        total = len(pending)
        print(f"\nRows to rebuild: {total}{' (limited)' if limit else ''}\n")
        if not total:
            print("Nothing to do.")
            return 0 if check_complete(before) else 1

        succeeded = 0
        missing_audio = 0
        failed: List[str] = []
        started = time.time()

        for i, row in enumerate(pending, 1):
            song_id = row["song_id"]
            title = row["title"] or "(no catalog row)"

            audio_path = readable_path(row)
            if audio_path is None:
                missing_audio += 1
                logger.warning(
                    f"[{i}/{total}] song {song_id} ({title}): no readable audio file "
                    f"for {row['audio_path']!r} - skipping"
                )
                continue

            resolved = str(audio_path.resolve())
            # Normalise this row's path before indexing, so index_audio_file's
            # ON CONFLICT (audio_path) updates this row rather than inserting a
            # second one for the same audio.
            if resolved != row["audio_path"]:
                async with db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE audio_embeddings SET audio_path = $2 WHERE id = $1",
                        row["id"],
                        resolved,
                    )

            if await rag.index_audio_file(resolved, song_id):
                succeeded += 1
            else:
                # index_audio_file has already logged why -- a missing CLAP half,
                # unreadable audio, or the write itself.
                failed.append(f"song {song_id} ({title}) at {resolved}")

            if i <= 5 or i % 25 == 0 or i == total:
                per_row = (time.time() - started) / i
                print(
                    f"  [{i}/{total}] {title[:44]:44s} "
                    f"ok={succeeded} failed={len(failed)} skipped={missing_audio} "
                    f"~{(total - i) * per_row / 60:.0f} min left"
                )

        print("\n" + "=" * 70)
        print(f"Re-index finished in {(time.time() - started) / 60:.1f} min")
        print(f"  rebuilt                : {succeeded}")
        print(f"  failed                 : {len(failed)}")
        print(f"  skipped (no audio file): {missing_audio}")
        for entry in failed[:25]:
            print(f"    FAILED {entry}")
        if len(failed) > 25:
            print(f"    ... and {len(failed) - 25} more (each reason is in the log above)")

        after = await read_status(db)
        print_status(after, "After:")
        return 0 if check_complete(after) else 1
    finally:
        await db.close()


async def status_only(check: bool) -> int:
    db = DatabaseManager()
    await db.connect()
    try:
        status = await read_status(db)
        print_status(status, "Audio index status:")
        if check:
            return 0 if check_complete(status) else 1
        return 0
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild every song's audio index with CLAP.")
    parser.add_argument(
        "--status", action="store_true", help="print the audio index counts and exit"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the counts and exit non-zero if any audio index is partial",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="rebuild at most N rows (for a smoke run)"
    )
    args = parser.parse_args()

    if args.status or args.check:
        raise SystemExit(asyncio.run(status_only(check=args.check)))
    raise SystemExit(asyncio.run(reindex(args.limit)))


if __name__ == "__main__":
    main()
