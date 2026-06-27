"""
Derive songs.genre from transcribed lyrics via the LLM (issue #52).

genre was defined in the schema but bigflavorband.com never provided it, so it
was never scraped or otherwise populated. This batch job asks the configured LLM
(via get_llm_provider, honouring the Ollama/Anthropic switch) to infer each
song's genre from its title, metadata, and transcribed lyrics, then writes the
label back to the songs table.

Genre is inferred *from lyrics* (the issue owner's decision): a song with no
stored lyrics is skipped and left null, never errored. Labels are constrained to
a small controlled vocabulary so the column stays consistent for
filtering/search. This mirrors src/rag/derive_energy_mood.py.

Usage (inside the backend container, where LLM + DB env is wired):
    docker exec bigflavor-backend python -m src.rag.derive_genre --status
    docker exec bigflavor-backend python -m src.rag.derive_genre --limit 5 --dry-run
    docker exec bigflavor-backend python -m src.rag.derive_genre            # all missing
    docker exec bigflavor-backend python -m src.rag.derive_genre --reindex  # redo all
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.llm.llm_provider import get_llm_provider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("derive-genre")

# Controlled vocabulary. Keep within songs.genre VARCHAR(100). Constraining the
# model's output keeps the column filterable and avoids a long tail of synonyms.
GENRE_LABELS = [
    "rock", "pop", "folk", "country", "blues", "jazz", "funk", "soul",
    "r&b", "hip-hop", "reggae", "metal", "punk", "electronic", "ambient",
    "classical", "gospel", "world", "experimental",
]

# Whisper lyrics can be long; cap what we send to keep prompts small and fast.
MAX_LYRICS_CHARS = 1500

SYSTEM_PROMPT = (
    "You are a music analyst. Given a song's metadata and lyrics, classify its "
    "single best-fitting genre. Base the genre primarily on the lyrics' themes, "
    "language, and style. Respond with ONLY a JSON object and nothing else, in "
    f'the form {{"genre": "<one of {GENRE_LABELS}>"}}. '
    "Choose exactly one value from the list."
)


async def fetch_songs(
    db: DatabaseManager, reindex: bool, limit: Optional[int]
) -> List[Dict[str, Any]]:
    """Fetch songs needing a genre, joined with their transcribed lyrics.

    Genre is inferred from lyrics, so songs with no stored lyrics are excluded
    here (INNER JOIN) — they are left null rather than guessed from metadata.
    """
    where = "" if reindex else "AND s.genre IS NULL"
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    query = f"""
        SELECT s.id, s.title, s.tempo_bpm, s.key, s.duration_seconds,
               te.content AS lyrics
        FROM songs s
        JOIN text_embeddings te
               ON te.song_id = s.id AND te.content_type = 'lyrics'
        WHERE te.content IS NOT NULL AND length(trim(te.content)) > 0
        {where}
        ORDER BY s.id
        {limit_sql}
    """
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) for r in rows]


def build_user_prompt(song: Dict[str, Any]) -> str:
    """Assemble the per-song prompt from available metadata and lyrics."""
    lines = [f"Title: {song['title']}"]
    if song.get("tempo_bpm"):
        lines.append(f"Tempo (BPM): {round(song['tempo_bpm'])}")
    if song.get("key"):
        lines.append(f"Key: {song['key']}")
    if song.get("duration_seconds"):
        lines.append(f"Duration (s): {song['duration_seconds']}")

    lyrics = (song.get("lyrics") or "").strip()
    if len(lyrics) > MAX_LYRICS_CHARS:
        lyrics = lyrics[:MAX_LYRICS_CHARS] + " […]"
    lines.append(f"\nLyrics:\n{lyrics}")

    return "\n".join(lines)


def parse_genre(text: str) -> Optional[str]:
    """Extract and validate a genre from the model's JSON reply."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        logger.warning(f"No JSON object in model reply: {text[:120]!r}")
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON in model reply: {text[start:end + 1][:120]!r}")
        return None

    genre = str(data.get("genre", "")).strip().lower()
    if genre not in GENRE_LABELS:
        logger.warning(f"Genre '{genre}' not in vocabulary; skipping")
        return None
    return genre


async def classify(llm, song: Dict[str, Any], temperature: float) -> Optional[str]:
    """Classify one song's genre, with a single corrective retry on bad output.

    Some songs draw an out-of-vocabulary label; the retry re-states the allowed
    list and asks for the closest valid label.
    """
    messages = [{"role": "user", "content": build_user_prompt(song)}]
    reply = await llm.generate_response(
        messages=messages, system=SYSTEM_PROMPT, max_tokens=100, temperature=temperature
    )
    genre = parse_genre(reply)
    if genre is not None:
        return genre

    messages.append({"role": "assistant", "content": reply})
    messages.append({
        "role": "user",
        "content": (
            "That was not a valid choice. Respond with ONLY JSON "
            f'{{"genre": <one of {GENRE_LABELS}>}}. '
            "Pick the single closest label from the list — do not invent a new one."
        ),
    })
    retry = await llm.generate_response(
        messages=messages, system=SYSTEM_PROMPT, max_tokens=100,
        temperature=min(1.0, temperature + 0.5),
    )
    return parse_genre(retry)


async def status(db: DatabaseManager) -> None:
    query = """
        SELECT COUNT(*) AS total,
               COUNT(genre) AS genre_filled,
               COUNT(*) FILTER (
                   WHERE EXISTS (
                       SELECT 1 FROM text_embeddings te
                       WHERE te.song_id = songs.id AND te.content_type = 'lyrics'
                   )
               ) AS with_lyrics
        FROM songs
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query)
    print("\nGenre status:")
    print(f"  Total songs       : {row['total']}")
    print(f"  genre set         : {row['genre_filled']}")
    print(f"  songs with lyrics : {row['with_lyrics']}")


async def derive(
    limit: Optional[int], reindex: bool, dry_run: bool, temperature: float
) -> None:
    db = DatabaseManager()
    await db.connect()
    llm = get_llm_provider()

    try:
        songs = await fetch_songs(db, reindex=reindex, limit=limit)
        total = len(songs)
        print("\n" + "=" * 70)
        print(f"Derive genre   ({'DRY RUN' if dry_run else 'APPLY'})")
        print("=" * 70)
        print(f"Songs to process: {total}")
        if not total:
            print("Nothing to do.")
            return

        update_sql = """
            UPDATE songs
            SET genre = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """

        succeeded = 0
        failed = 0
        for i, song in enumerate(songs, 1):
            try:
                genre = await classify(llm, song, temperature)
                if genre is None:
                    failed += 1
                    continue

                if not dry_run:
                    async with db.pool.acquire() as conn:
                        await conn.execute(update_sql, song["id"], genre)

                succeeded += 1
                if dry_run or i <= 10 or i % 50 == 0:
                    print(f"  [{i}/{total}] {song['title'][:45]:45s} -> {genre}")
            except Exception as e:
                failed += 1
                logger.error(f"Song {song['id']} ({song['title']}): {e}")

        print("\n" + "-" * 70)
        print(f"Classified: {succeeded}   Failed/skipped: {failed}")
        if dry_run:
            print("DRY RUN -- no changes written. Re-run without --dry-run to commit.")
        else:
            print("[OK] genre written.")
            await status(db)
    finally:
        # OllamaProvider holds an httpx client; close it if present.
        close = getattr(llm, "close", None)
        if close:
            await close()
        await db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive songs.genre from lyrics via the LLM."
    )
    parser.add_argument("--status", action="store_true", help="Show fill status and exit.")
    parser.add_argument("--limit", type=int, help="Process at most N songs.")
    parser.add_argument(
        "--reindex", action="store_true", help="Reprocess all songs, not just missing ones."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Classify and print without writing."
    )
    parser.add_argument(
        "--temperature", type=float, default=0.2, help="LLM sampling temperature (default 0.2)."
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

    await derive(
        limit=args.limit,
        reindex=args.reindex,
        dry_run=args.dry_run,
        temperature=args.temperature,
    )


if __name__ == "__main__":
    asyncio.run(main())
