"""
Derive songs.energy and songs.mood via the LLM.

These two columns were defined in the schema but never populated — no analysis
step ever wrote them. This batch job asks the configured LLM (via
get_llm_provider, honouring the Ollama/Anthropic switch) to classify each song's
energy and mood from its title, metadata, and transcribed lyrics, then writes
the labels back to the songs table.

Labels are constrained to a small controlled vocabulary so the columns stay
consistent and useful for filtering/search.

Usage (inside the backend container, where LLM + DB env is wired):
    docker exec bigflavor-backend python -m src.rag.derive_energy_mood --status
    docker exec bigflavor-backend python -m src.rag.derive_energy_mood --limit 5 --dry-run
    docker exec bigflavor-backend python -m src.rag.derive_energy_mood            # all missing
    docker exec bigflavor-backend python -m src.rag.derive_energy_mood --reindex  # redo all
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
logger = logging.getLogger("derive-energy-mood")

# Controlled vocabularies. Keep energy within VARCHAR(20) and mood within
# VARCHAR(50). Constraining the model's output keeps the columns filterable.
ENERGY_LABELS = ["low", "medium", "high"]
MOOD_LABELS = [
    "happy", "uplifting", "energetic", "playful", "romantic", "peaceful",
    "calm", "nostalgic", "melancholic", "somber", "dark", "aggressive",
    "mysterious", "hopeful",
]

# Whisper lyrics can be long; cap what we send to keep prompts small and fast.
MAX_LYRICS_CHARS = 1500

SYSTEM_PROMPT = (
    "You are a music analyst. Given a song's metadata and lyrics, classify its "
    "overall energy and mood. Energy reflects intensity/drive; mood reflects "
    "emotional character. Respond with ONLY a JSON object and nothing else, "
    f'in the form {{"energy": "<one of {ENERGY_LABELS}>", '
    f'"mood": "<one of {MOOD_LABELS}>"}}. '
    "Choose exactly one value from each list. If the song is instrumental or "
    "lyrics are unclear, infer from tempo, key, and title."
)


async def fetch_songs(
    db: DatabaseManager, reindex: bool, limit: Optional[int]
) -> List[Dict[str, Any]]:
    """Fetch songs needing energy/mood, joined with their transcribed lyrics."""
    where = "" if reindex else "WHERE (s.energy IS NULL OR s.mood IS NULL)"
    limit_sql = f"LIMIT {int(limit)}" if limit else ""
    query = f"""
        SELECT s.id, s.title, s.genre, s.tempo_bpm, s.key, s.duration_seconds,
               te.content AS lyrics
        FROM songs s
        LEFT JOIN text_embeddings te
               ON te.song_id = s.id AND te.content_type = 'lyrics'
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
    if song.get("genre"):
        lines.append(f"Genre: {song['genre']}")
    if song.get("tempo_bpm"):
        lines.append(f"Tempo (BPM): {round(song['tempo_bpm'])}")
    if song.get("key"):
        lines.append(f"Key: {song['key']}")
    if song.get("duration_seconds"):
        lines.append(f"Duration (s): {song['duration_seconds']}")

    lyrics = (song.get("lyrics") or "").strip()
    if lyrics:
        if len(lyrics) > MAX_LYRICS_CHARS:
            lyrics = lyrics[:MAX_LYRICS_CHARS] + " […]"
        lines.append(f"\nLyrics:\n{lyrics}")
    else:
        lines.append("\nLyrics: (none — likely instrumental)")

    return "\n".join(lines)


def parse_classification(text: str) -> Optional[Tuple[str, str]]:
    """Extract and validate (energy, mood) from the model's JSON reply."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        logger.warning(f"No JSON object in model reply: {text[:120]!r}")
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON in model reply: {text[start:end + 1][:120]!r}")
        return None

    energy = str(data.get("energy", "")).strip().lower()
    mood = str(data.get("mood", "")).strip().lower()
    if energy not in ENERGY_LABELS:
        logger.warning(f"Energy '{energy}' not in vocabulary; skipping")
        return None
    if mood not in MOOD_LABELS:
        logger.warning(f"Mood '{mood}' not in vocabulary; skipping")
        return None
    return energy, mood


async def status(db: DatabaseManager) -> None:
    query = """
        SELECT COUNT(*) AS total,
               COUNT(energy) AS energy_filled,
               COUNT(mood) AS mood_filled
        FROM songs
    """
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query)
    print("\nEnergy/Mood status:")
    print(f"  Total songs : {row['total']}")
    print(f"  energy set  : {row['energy_filled']}")
    print(f"  mood set    : {row['mood_filled']}")


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
        print(f"Derive energy/mood   ({'DRY RUN' if dry_run else 'APPLY'})")
        print("=" * 70)
        print(f"Songs to process: {total}")
        if not total:
            print("Nothing to do.")
            return

        update_sql = """
            UPDATE songs
            SET energy = $2, mood = $3, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """

        succeeded = 0
        failed = 0
        for i, song in enumerate(songs, 1):
            try:
                reply = await llm.generate_response(
                    messages=[{"role": "user", "content": build_user_prompt(song)}],
                    system=SYSTEM_PROMPT,
                    max_tokens=200,
                    temperature=temperature,
                )
                result = parse_classification(reply)
                if result is None:
                    failed += 1
                    continue
                energy, mood = result

                if not dry_run:
                    async with db.pool.acquire() as conn:
                        await conn.execute(update_sql, song["id"], energy, mood)

                succeeded += 1
                if dry_run or i <= 10 or i % 50 == 0:
                    print(f"  [{i}/{total}] {song['title'][:45]:45s} -> {energy}, {mood}")
            except Exception as e:
                failed += 1
                logger.error(f"Song {song['id']} ({song['title']}): {e}")

        print("\n" + "-" * 70)
        print(f"Classified: {succeeded}   Failed/skipped: {failed}")
        if dry_run:
            print("DRY RUN -- no changes written. Re-run without --dry-run to commit.")
        else:
            print("[OK] energy/mood written.")
            await status(db)
    finally:
        # OllamaProvider holds an httpx client; close it if present.
        close = getattr(llm, "close", None)
        if close:
            await close()
        await db.close()


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Derive songs.energy and songs.mood via the LLM."
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
