"""
Batch Lyrics Indexing Script
Extracts lyrics from audio files in the library and indexes them for RAG search.
Uses Demucs for vocal separation and faster-whisper for transcription.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Tuple, Optional
import json
from datetime import datetime
import sys
from urllib.parse import unquote

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database import DatabaseManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("index-lyrics")


async def get_audio_files_without_lyrics(db: DatabaseManager) -> List[Tuple[Optional[str], str, str]]:
    """
    Get audio files from audio_library that don't have lyrics indexed yet.
    Matches MP3 filenames (which are based on song titles) with database songs.
    
    Returns:
        List of (song_id, filename, audio_path) tuples
        song_id will be None if the file isn't in the database
    """
    audio_library = project_root / "audio_library"
    if not audio_library.exists():
        logger.warning(f"Audio library not found: {audio_library}")
        return []
    
    # Get all MP3 files
    audio_files = list(audio_library.glob("*.mp3"))
    logger.info(f"Found {len(audio_files)} audio files in {audio_library}")
    
    # Get songs with their titles and check if lyrics exist
    query = """
        SELECT s.id, s.title,
               EXISTS(
                   SELECT 1 FROM text_embeddings te
                   WHERE te.song_id = s.id AND te.content_type = 'lyrics'
               ) as has_lyrics
        FROM songs s
        WHERE s.audio_url IS NOT NULL
        AND s.audio_url != ''
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    
    # Create mapping of title -> (song_id, has_lyrics)
    song_map = {}
    for row in rows:
        title = row['title']
        song_id = row['id']
        has_lyrics = row['has_lyrics']
        # Store by title (case-insensitive)
        song_map[title.lower()] = (song_id, has_lyrics)
    
    logger.info(f"Found {sum(1 for _, hl in song_map.values() if hl)} songs already with lyrics")
    
    # Match audio files to songs by title
    results = []
    matched = 0
    for audio_path in audio_files:
        # Remove .mp3 extension to get title
        filename = audio_path.name
        title = audio_path.stem  # filename without extension
        
        # Try to find matching song by title
        title_lower = title.lower()
        if title_lower in song_map:
            song_id, has_lyrics = song_map[title_lower]
            if not has_lyrics:
                results.append((song_id, filename, str(audio_path)))
                matched += 1
    
    logger.info(f"Matched {matched} audio files to songs in database without lyrics")
    
    return results


async def get_all_songs_with_audio(db: DatabaseManager, audio_library_path: Path) -> List[Tuple[str, str, str]]:
    """
    Get all songs that have local audio files.
    
    Args:
        db: Database manager
        audio_library_path: Path to audio library directory
        
    Returns:
        List of (song_id, title, audio_path) tuples
    """
    query = """
        SELECT id, title, audio_url
        FROM songs
        WHERE audio_url IS NOT NULL
        AND audio_url != ''
        ORDER BY title
    """
    
    async with db.pool.acquire() as conn:
        rows = await conn.fetch(query)
    
    results = []
    for row in rows:
        song_id = row['id']
        title = row['title']
        audio_url = row['audio_url']
        
        if audio_url:
            filename = Path(audio_url).name
            local_path = audio_library_path / filename
            
            if local_path.exists():
                results.append((song_id, title, str(local_path)))
    
    return results


async def check_lyrics_status(db: DatabaseManager):
    """Check how many songs have lyrics indexed."""
    query = """
        SELECT 
            COUNT(DISTINCT s.id) as total_songs,
            COUNT(DISTINCT te.song_id) as songs_with_lyrics,
            COUNT(DISTINCT s.id) - COUNT(DISTINCT te.song_id) as songs_without_lyrics
        FROM songs s
        LEFT JOIN text_embeddings te ON s.id = te.song_id AND te.content_type = 'lyrics'
        WHERE s.audio_url IS NOT NULL
        AND s.audio_url != ''
    """
    
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(query)
    
    return dict(row)


async def index_lyrics_batch(
    audio_library_path: str = "audio_library",
    max_songs: Optional[int] = None,
    separate_vocals: bool = True,
    min_confidence: float = 0.5,
    reindex: bool = False
):
    """
    Index lyrics for songs in the audio library.
    
    Args:
        audio_library_path: Path to audio library directory
        max_songs: Maximum number of songs to process (None for all)
        separate_vocals: Whether to use Demucs for vocal separation
        min_confidence: Minimum transcription confidence threshold
        reindex: Whether to reindex songs that already have lyrics
    """
    print("\n" + "="*70)
    print("Lyrics Batch Indexing")
    print("="*70)
    
    # Initialize database
    db = DatabaseManager()
    await db.connect()
    
    # Initialize RAG system
    rag = SongRAGSystem(db, use_clap=False)  # Don't need CLAP for lyrics
    
    try:
        # Check current status
        print("\nChecking current lyrics status...")
        status = await check_lyrics_status(db)
        
        print(f"\nCurrent Status:")
        print(f"  Total songs with audio: {status['total_songs']}")
        print(f"  Songs with lyrics: {status['songs_with_lyrics']}")
        print(f"  Songs without lyrics: {status['songs_without_lyrics']}")
        
        # Get songs to process
        audio_lib = Path(audio_library_path)
        if not audio_lib.exists():
            print(f"\n❌ Audio library not found: {audio_library_path}")
            return
        
        if reindex:
            print("\nFetching all songs for reindexing...")
            songs = await get_all_songs_with_audio(db, audio_lib)
        else:
            print("\nFetching songs without lyrics...")
            songs = await get_audio_files_without_lyrics(db)
        
        if not songs:
            print("\nAll audio files already have lyrics indexed!")
            return
        
        if max_songs:
            songs = songs[:max_songs]
        
        total = len(songs)
        print(f"\nSettings:")
        print(f"  Vocal separation: {separate_vocals}")
        print(f"  Minimum confidence: {min_confidence}")
        print(f"  Reindex existing: {reindex}")
        
        # Confirm before proceeding
        if len(songs) > 10:
            response = input(f"\nProcess {len(songs)} songs? This may take a while. (y/n): ")
            if response.lower() != 'y':
                print("Cancelled.")
                return
        
        print("\n" + "-"*70)
        print("Starting lyrics extraction...")
        print("-"*70 + "\n")
        
        # Filter to only songs with valid song_id (in database)
        songs_with_id = [(song_id, filename, path) for song_id, filename, path in songs if song_id is not None]
        songs_without_id = [(song_id, filename, path) for song_id, filename, path in songs if song_id is None]
        
        if songs_without_id:
            print(f"\nSkipping {len(songs_without_id)} files not found in database:")
            for _, filename, _ in songs_without_id[:5]:
                print(f"  - {filename}")
            if len(songs_without_id) > 5:
                print(f"  ... and {len(songs_without_id) - 5} more")
        
        if not songs_with_id:
            print("\nNo songs with database entries to process.")
            return
        
        print(f"\nProcessing {len(songs_with_id)} songs found in database...")
        
        # Extract audio paths
        audio_files = [(path, song_id) for song_id, filename, path in songs_with_id]
        
        # Batch extract lyrics
        stats = await rag.batch_extract_lyrics(
            audio_files,
            separate_vocals=separate_vocals,
            min_confidence=min_confidence
        )
        
        # Display results
        print("\n" + "="*70)
        print("Lyrics Extraction Summary")
        print("="*70)
        print(f"\nTotal processed: {stats['total']}")
        print(f"✓ Successful: {stats['success']}")
        print(f"✗ Failed: {stats['failed']}")
        print(f"⚠ Low confidence: {stats['low_confidence_count']}")
        
        if stats['low_confidence_songs']:
            print(f"\nLow confidence songs (< 70%):")
            for song_id, conf in stats['low_confidence_songs'][:10]:
                print(f"  - {song_id}: {conf:.1%}")
            if len(stats['low_confidence_songs']) > 10:
                print(f"  ... and {len(stats['low_confidence_songs']) - 10} more")
        
        if stats['failed_files']:
            print(f"\nFailed songs:")
            for path, song_id, error in stats['failed_files'][:10]:
                print(f"  - {song_id}: {error}")
            if len(stats['failed_files']) > 10:
                print(f"  ... and {len(stats['failed_files']) - 10} more")
        
        # Save detailed report
        report_file = project_root / f"lyrics_indexing_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        print(f"\nDetailed report saved to: {report_file}")
        
        # Check updated status
        print("\nUpdated lyrics status:")
        status = await check_lyrics_status(db)
        print(f"  Total songs with audio: {status['total_songs']}")
        print(f"  Songs with lyrics: {status['songs_with_lyrics']}")
        print(f"  Songs without lyrics: {status['songs_without_lyrics']}")
        
    finally:
        await db.close()


async def test_single_song(audio_path: str):
    """
    Test lyrics extraction on a single audio file.
    
    Args:
        audio_path: Path to audio file
    """
    print("\n" + "="*70)
    print("Single Song Lyrics Extraction Test")
    print("="*70)
    
    audio_file = Path(audio_path)
    if not audio_file.exists():
        print(f"\n❌ Audio file not found: {audio_path}")
        return
    
    print(f"\nProcessing: {audio_file.name}")
    
    # Initialize database
    db = DatabaseManager()
    await db.connect()
    
    try:
        # Initialize RAG system
        rag = SongRAGSystem(db, use_clap=False)
        
        # Try to find song ID
        query = """
            SELECT id, title FROM songs
            WHERE audio_url LIKE $1
            LIMIT 1
        """
        
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(query, f"%{audio_file.name}%")
        
        if row:
            song_id = row['id']
            title = row['title']
            print(f"Found in database: {title} (ID: {song_id})")
        else:
            song_id = f"test_{audio_file.stem}"
            print(f"Not in database, using temporary ID: {song_id}")
        
        print("\nExtracting lyrics...")
        
        # Extract lyrics
        result = await rag.extract_and_index_lyrics(
            audio_path=str(audio_file),
            song_id=song_id,
            separate_vocals=True,
            min_confidence=0.5,
            generate_embedding=False
        )
        
        # Display results
        print("\n" + "="*70)
        print("Results")
        print("="*70)
        
        if result['success']:
            print(f"\n✓ Lyrics extracted successfully!")
            print(f"\nConfidence: {result.get('confidence', 0):.1%}")
            print(f"Segments: {result.get('segments', 0)}")
            print(f"\n{'='*70}")
            print("LYRICS")
            print(f"{'='*70}\n")
            print(result.get('lyrics', ''))
        else:
            print(f"\n❌ Extraction failed: {result.get('error', 'Unknown error')}")
        
    finally:
        await db.close()


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract and index lyrics from audio files')
    parser.add_argument('--audio-library', default='audio_library', help='Path to audio library')
    parser.add_argument('--max-songs', type=int, help='Maximum number of songs to process')
    parser.add_argument('--no-vocal-separation', action='store_true', help='Skip vocal separation (faster but less accurate)')
    parser.add_argument('--min-confidence', type=float, default=0.5, help='Minimum transcription confidence (0-1)')
    parser.add_argument('--reindex', action='store_true', help='Reindex songs that already have lyrics')
    parser.add_argument('--test', help='Test on a single audio file')
    parser.add_argument('--status', action='store_true', help='Check lyrics indexing status')
    
    args = parser.parse_args()
    
    if args.test:
        await test_single_song(args.test)
    elif args.status:
        db = DatabaseManager()
        await db.connect()
        try:
            status = await check_lyrics_status(db)
            print("\nLyrics Indexing Status:")
            print(f"  Total songs with audio: {status['total_songs']}")
            print(f"  Songs with lyrics: {status['songs_with_lyrics']}")
            print(f"  Songs without lyrics: {status['songs_without_lyrics']}")
        finally:
            await db.close()
    else:
        await index_lyrics_batch(
            audio_library_path=args.audio_library,
            max_songs=args.max_songs,
            separate_vocals=not args.no_vocal_separation,
            min_confidence=args.min_confidence,
            reindex=args.reindex
        )


if __name__ == '__main__':
    asyncio.run(main())
