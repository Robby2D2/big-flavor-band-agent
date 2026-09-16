"""Give every song all the mood and genre labels that apply, not just one.

Seeds song_tags from the single mood/genre columns (lossless, instant), then
asks the model for any further labels that genuinely fit. Additive: a song keeps
its primary label and simply gains the others.

Resumable — songs that already have derived tags are skipped — so a run that is
interrupted picks up where it stopped.

Usage:
    docker exec bigflavor-backend python scripts/backfill_song_tags.py
"""
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager
from src.llm.llm_provider import get_llm_provider
from src.rag.song_tags import SYSTEM_PROMPT, build_tagging_prompt, parse_tags

SEED_SQL = """
    INSERT INTO song_tags (song_id, kind, value, source)
    SELECT id, 'mood', lower(mood), 'primary' FROM songs
    WHERE mood IS NOT NULL AND mood <> ''
    ON CONFLICT (song_id, kind, value) DO NOTHING
"""

SEED_GENRE_SQL = """
    INSERT INTO song_tags (song_id, kind, value, source)
    SELECT id, 'genre', lower(genre), 'primary' FROM songs
    WHERE genre IS NOT NULL AND genre <> ''
    ON CONFLICT (song_id, kind, value) DO NOTHING
"""


async def backfill() -> None:
    db = DatabaseManager()
    await db.connect()

    try:
        async with db.pool.acquire() as conn:
            await conn.execute(SEED_SQL)
            await conn.execute(SEED_GENRE_SQL)
            seeded = await conn.fetchval("SELECT count(*) FROM song_tags WHERE source='primary'")
        print(f"Seeded {seeded} primary tags from the existing columns")

        async with db.pool.acquire() as conn:
            songs = await conn.fetch("""
                SELECT s.id, s.title, s.genre, s.mood, s.energy, s.key, s.tempo_bpm,
                       te.content AS lyrics
                FROM songs s
                LEFT JOIN text_embeddings te
                       ON te.song_id = s.id AND te.content_type = 'lyrics'
                WHERE NOT EXISTS (
                    SELECT 1 FROM song_tags t
                    WHERE t.song_id = s.id AND t.source = 'derived'
                )
                ORDER BY s.id
            """)

        print(f"Songs still needing derived tags: {len(songs)}")
        if not songs:
            return

        llm = get_llm_provider()
        added = 0

        for index, song in enumerate(songs, 1):
            record = dict(song)
            try:
                reply = await llm.generate_response(
                    messages=[{"role": "user",
                               "content": build_tagging_prompt(record, record.get("lyrics"))}],
                    system=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_tokens=200,
                )
                tags = parse_tags(reply)
            except Exception as exc:
                print(f"  #{record['id']} failed: {exc}")
                continue

            rows = [(record["id"], "mood", m, "derived") for m in tags["moods"]]
            rows += [(record["id"], "genre", g, "derived") for g in tags["genres"]]
            if rows:
                async with db.pool.acquire() as conn:
                    await conn.executemany(
                        """
                        INSERT INTO song_tags (song_id, kind, value, source)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (song_id, kind, value) DO NOTHING
                        """,
                        rows,
                    )
                added += len(rows)

            if index % 25 == 0 or index == len(songs):
                print(f"  {index}/{len(songs)} songs · {added} tags added")

        async with db.pool.acquire() as conn:
            stats = await conn.fetch("""
                SELECT kind, source, count(*) AS n FROM song_tags
                GROUP BY kind, source ORDER BY kind, source
            """)
        print("\nsong_tags now holds:")
        for row in stats:
            print(f"  {row['kind']:6s} {row['source']:8s} {row['n']}")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(backfill())
