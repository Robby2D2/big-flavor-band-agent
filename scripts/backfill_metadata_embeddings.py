"""Embed each song's metadata so semantic search can match on what a song *is*.

Until this ran, `text_embeddings` held only `content_type='lyrics'`, so a query
like "melancholic country" could only match songs whose words happened to
contain those terms — a song's own genre, mood and energy were invisible to
semantic search. This adds one `content_type='metadata'` row per song.

Idempotent: re-running refreshes every row (upsert on song_id + content_type),
so run it again after a metadata back-fill or a re-tagging sweep.

Usage (inside the backend container, which already has the model cached + GPU):
    docker exec bigflavor-backend python scripts/backfill_metadata_embeddings.py
"""
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sentence_transformers import SentenceTransformer

from database import DatabaseManager
from src.rag.search_text import build_metadata_text

# Must match the model and dimensions the search path uses (see SongRAGSystem).
MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 128

UPSERT = """
    INSERT INTO text_embeddings (song_id, content_type, content, embedding)
    VALUES ($1, 'metadata', $2, $3)
    ON CONFLICT (song_id, content_type) DO UPDATE SET
        content = EXCLUDED.content,
        embedding = EXCLUDED.embedding,
        created_at = CURRENT_TIMESTAMP
"""


async def backfill() -> None:
    db = DatabaseManager()
    await db.connect()

    try:
        async with db.pool.acquire() as conn:
            songs = await conn.fetch("""
                SELECT id, title, genre, mood, energy, tempo_bpm, key
                FROM songs
                ORDER BY id
            """)

        print(f"Songs in catalog: {len(songs)}")

        pending = []
        for song in songs:
            text = build_metadata_text(dict(song))
            if text:
                pending.append((song["id"], text))

        skipped = len(songs) - len(pending)
        if skipped:
            print(f"Skipping {skipped} song(s) with no usable metadata")

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading {MODEL_NAME} on {device}...")
        model = SentenceTransformer(MODEL_NAME, device=device)

        written = 0
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            vectors = model.encode([text for _, text in batch], batch_size=BATCH_SIZE)

            rows = [
                (song_id, text, str(vector.tolist()))
                for (song_id, text), vector in zip(batch, vectors)
            ]
            async with db.pool.acquire() as conn:
                await conn.executemany(UPSERT, rows)

            written += len(rows)
            print(f"  embedded {written}/{len(pending)}")

        async with db.pool.acquire() as conn:
            counts = await conn.fetch("""
                SELECT content_type, count(*) AS rows
                FROM text_embeddings
                GROUP BY content_type
                ORDER BY content_type
            """)

        print("\ntext_embeddings now holds:")
        for row in counts:
            print(f"  {row['content_type']:10s} {row['rows']}")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(backfill())
