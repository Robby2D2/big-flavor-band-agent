"""Embed verse-sized lyric chunks so songs are found by the part that matches.

A whole song's lyrics were one 384-dim vector — 850 characters averaged into a
single point, which buried any specific subject. This splits each song's lyrics
into overlapping chunks and embeds each one.

Idempotent: a song's chunks are replaced wholesale, so re-run after a lyric
re-extraction or a change to the chunk size.

Usage (inside the backend container, which has the model cached + GPU):
    docker exec bigflavor-backend python scripts/backfill_lyric_chunks.py
"""
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sentence_transformers import SentenceTransformer

from database import DatabaseManager
from src.rag.lyric_chunks import chunk_lyrics

MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 256


async def backfill() -> None:
    db = DatabaseManager()
    await db.connect()

    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT song_id, content
                FROM text_embeddings
                WHERE content_type = 'lyrics' AND content IS NOT NULL
                ORDER BY song_id
            """)

        print(f"Songs with lyrics: {len(rows)}")

        pending = []  # (song_id, chunk_index, text)
        for row in rows:
            for index, chunk in enumerate(chunk_lyrics(row["content"])):
                pending.append((row["song_id"], index, chunk))

        songs_with_chunks = len({p[0] for p in pending})
        print(f"Chunks to embed: {len(pending)} across {songs_with_chunks} songs "
              f"({len(pending) / max(songs_with_chunks, 1):.1f} per song)")

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Loading {MODEL_NAME} on {device}...")
        model = SentenceTransformer(MODEL_NAME, device=device)

        # Replace wholesale so a re-run after a chunk-size change leaves no
        # orphaned chunks from the previous shape.
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM song_lyric_chunks WHERE song_id = ANY($1::int[])",
                list({p[0] for p in pending}),
            )

        written = 0
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start:start + BATCH_SIZE]
            vectors = model.encode([text for _, _, text in batch], batch_size=BATCH_SIZE)

            async with db.pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO song_lyric_chunks (song_id, chunk_index, content, embedding)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (song_id, chunk_index) DO UPDATE SET
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                    """,
                    [
                        (song_id, index, text, str(vector.tolist()))
                        for (song_id, index, text), vector in zip(batch, vectors)
                    ],
                )

            written += len(batch)
            print(f"  embedded {written}/{len(pending)}")

        async with db.pool.acquire() as conn:
            total = await conn.fetchval("SELECT count(*) FROM song_lyric_chunks")
            songs = await conn.fetchval("SELECT count(DISTINCT song_id) FROM song_lyric_chunks")
        print(f"\nsong_lyric_chunks now holds {total} chunks across {songs} songs")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(backfill())
