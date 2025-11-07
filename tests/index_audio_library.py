"""
Batch Audio Indexing Script
Indexes all audio files in the library to create embeddings for RAG system.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Tuple
import json
from datetime import datetime

from database import DatabaseManager
from rag_system import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("index-audio")


async def get_songs_to_index(db: DatabaseManager, audio_library_path: Path) -> List[Tuple[str, str]]:
    """
    Get list of songs that need indexing.
    Matches songs in database with audio files in the library.
    
    Returns:
        List of (audio_path, song_id) tuples
    """
    # Get all audio files
    audio_files = {}
    for audio_file in audio_library_path.glob("*.mp3"):
        audio_files[audio_file.stem] = str(audio_file)
    
    logger.info(f"Found {len(audio_files)} audio files in library")
    
    # Get songs from database that don't have embeddings
    query = """
        SELECT s.id, s.title
        FROM songs s
        LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
        WHERE ae.id IS NULL
        ORDER BY s.title
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    
    logger.info(f"Found {len(rows)} songs without embeddings in database")
    
    # Match songs with audio files
    to_index = []
    unmatched = []
    
    for row in rows:
        song_id = row['id']
        title = row['title']
        
        # Try to find matching audio file
        # Clean up the title to match filenames
        clean_title = title.replace('/', '-').replace('\\', '-')
        
        if clean_title in audio_files:
            to_index.append((audio_files[clean_title], song_id))
        else:
            # Try partial matching
            matches = [f for fname, f in audio_files.items() if clean_title.lower() in fname.lower()]
            if matches:
                to_index.append((matches[0], song_id))
            else:
                unmatched.append((song_id, title))
    
    logger.info(f"Matched {len(to_index)} songs with audio files")
    
    if unmatched:
        logger.warning(f"Could not match {len(unmatched)} songs:")
        for song_id, title in unmatched[:10]:
            logger.warning(f"  - {title} (ID: {song_id})")
        if len(unmatched) > 10:
            logger.warning(f"  ... and {len(unmatched) - 10} more")
    
    return to_index


async def index_all_audio(
    audio_library_path: str = "audio_library",
    use_clap: bool = True,
    batch_size: int = 50
):
    """
    Index all audio files in the library.
    
    Args:
        audio_library_path: Path to audio library directory
        use_clap: Whether to use CLAP model (requires GPU for speed)
        batch_size: Process this many files before saving progress
    """
    audio_path = Path(audio_library_path)
    
    if not audio_path.exists():
        logger.error(f"Audio library path not found: {audio_path}")
        return
    
    # Initialize database and RAG system
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db, use_clap=use_clap)
    
    # Get initial stats
    stats = await rag.get_embedding_stats()
    logger.info(f"Initial state: {stats['songs_with_audio_embeddings']}/{stats['total_songs']} songs indexed")
    
    # Get songs to index
    to_index = await get_songs_to_index(db, audio_path)
    
    if not to_index:
        logger.info("All songs are already indexed!")
        await db.close()
        return
    
    # Process in batches
    total = len(to_index)
    processed = 0
    successful = 0
    failed = []
    
    start_time = datetime.now()
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Starting indexing of {total} audio files")
    logger.info(f"Using CLAP: {use_clap}")
    logger.info(f"{'='*60}\n")
    
    for i in range(0, total, batch_size):
        batch = to_index[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        
        logger.info(f"\n--- Batch {batch_num}/{total_batches} ---")
        
        # Process batch
        results = await rag.index_audio_batch(batch)
        
        processed += results['total']
        successful += results['success']
        failed.extend(results['failed_files'])
        
        # Progress update
        elapsed = (datetime.now() - start_time).total_seconds()
        rate = processed / elapsed if elapsed > 0 else 0
        remaining = (total - processed) / rate if rate > 0 else 0
        
        logger.info(f"Progress: {processed}/{total} ({processed/total*100:.1f}%)")
        logger.info(f"Success rate: {successful}/{processed} ({successful/processed*100:.1f}%)")
        logger.info(f"Processing rate: {rate:.2f} files/second")
        logger.info(f"Estimated time remaining: {remaining/60:.1f} minutes")
    
    # Final summary
    elapsed_minutes = (datetime.now() - start_time).total_seconds() / 60
    
    logger.info(f"\n{'='*60}")
    logger.info(f"INDEXING COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"Total processed: {processed}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {len(failed)}")
    logger.info(f"Time elapsed: {elapsed_minutes:.2f} minutes")
    logger.info(f"Average rate: {processed/elapsed_minutes:.1f} files/minute")
    
    if failed:
        logger.warning(f"\nFailed files:")
        for audio_path, song_id in failed:
            logger.warning(f"  - {Path(audio_path).name} (song_id: {song_id})")
    
    # Final stats
    final_stats = await rag.get_embedding_stats()
    logger.info(f"\nFinal state: {final_stats['songs_with_audio_embeddings']}/{final_stats['total_songs']} songs indexed")
    
    # Save report
    report = {
        'timestamp': datetime.now().isoformat(),
        'total_processed': processed,
        'successful': successful,
        'failed_count': len(failed),
        'failed_files': failed,
        'elapsed_minutes': elapsed_minutes,
        'use_clap': use_clap,
        'initial_stats': stats,
        'final_stats': final_stats
    }
    
    report_path = Path('audio_indexing_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"\nReport saved to: {report_path}")
    
    await db.close()


async def reindex_single_song(song_id: str, audio_path: str, use_clap: bool = True):
    """
    Re-index a single song (useful for debugging or updates).
    
    Args:
        song_id: Song ID in database
        audio_path: Path to audio file
        use_clap: Whether to use CLAP model
    """
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db, use_clap=use_clap)
    
    logger.info(f"Re-indexing song {song_id}: {audio_path}")
    
    success = await rag.index_audio_file(audio_path, song_id)
    
    if success:
        logger.info("✓ Successfully indexed")
    else:
        logger.error("✗ Failed to index")
    
    await db.close()


async def check_indexing_status():
    """
    Check which songs have been indexed.
    """
    db = DatabaseManager()
    await db.connect()
    
    rag = SongRAGSystem(db)
    
    # Get stats
    stats = await rag.get_embedding_stats()
    
    print("\n=== Audio Embedding Status ===")
    print(f"Total songs: {stats['total_songs']}")
    print(f"Songs with audio embeddings: {stats['songs_with_audio_embeddings']}")
    print(f"Songs with text embeddings: {stats['songs_with_text_embeddings']}")
    print(f"Average tempo: {stats.get('avg_tempo', 'N/A')}")
    
    # Find songs without embeddings
    missing = await rag.find_songs_without_embeddings()
    
    if missing:
        print(f"\n{len(missing)} songs without embeddings:")
        for song in missing[:20]:
            print(f"  - {song['title']} (ID: {song['id']})")
        if len(missing) > 20:
            print(f"  ... and {len(missing) - 20} more")
    else:
        print("\n✓ All songs are indexed!")
    
    await db.close()


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'status':
            asyncio.run(check_indexing_status())
        elif command == 'reindex' and len(sys.argv) >= 4:
            song_id = sys.argv[2]
            audio_path = sys.argv[3]
            asyncio.run(reindex_single_song(song_id, audio_path))
        else:
            print("Usage:")
            print("  python index_audio_library.py              # Index all songs")
            print("  python index_audio_library.py status       # Check indexing status")
            print("  python index_audio_library.py reindex <song_id> <audio_path>")
    else:
        # Default: index all
        asyncio.run(index_all_audio())
