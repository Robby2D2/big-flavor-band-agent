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
    separate_vocals: bool = False,
    min_confidence: float = 0.5,
    reindex: bool = False,
    skip_confirmation: bool = False,
    vad_filter: bool = False,
    vad_min_silence_ms: int = 2000,
    vad_threshold: float = 0.3,
    apply_voice_filter: bool = False,
    whisper_model_size: str = 'large-v3'
):
    """
    Index lyrics for songs in the audio library.
    
    Args:
        audio_library_path: Path to audio library directory
        max_songs: Maximum number of songs to process (None for all)
        separate_vocals: Whether to use Demucs for vocal separation (slow)
        min_confidence: Minimum transcription confidence threshold
        reindex: Whether to reindex songs that already have lyrics
        skip_confirmation: Skip confirmation prompt for batch processing
        vad_filter: Enable voice activity detection (filters silence)
        vad_min_silence_ms: Minimum silence duration in ms before filtering (default 2000 = 2 seconds)
        vad_threshold: VAD sensitivity 0.0-1.0 (lower = more sensitive, default 0.3)
        apply_voice_filter: Apply voice frequency bandpass filter (80-8000 Hz)
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
        if len(songs) > 10 and not skip_confirmation:
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
            min_confidence=min_confidence,
            vad_filter=vad_filter,
            vad_min_silence_ms=vad_min_silence_ms,
            vad_threshold=vad_threshold,
            apply_voice_filter=apply_voice_filter,
            whisper_model_size=whisper_model_size
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


async def test_single_song(audio_path: str, whisper_model_size: str = 'large-v3'):
    """
    Test lyrics extraction on a single audio file (does not write to database).
    
    Args:
        audio_path: Path to audio file
        whisper_model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3')
    """
    print("\n" + "="*70)
    print("Single Song Lyrics Extraction Test")
    print("="*70)
    
    audio_file = Path(audio_path)
    if not audio_file.exists():
        print(f"\n❌ Audio file not found: {audio_path}")
        return
    
    print(f"\nProcessing: {audio_file.name}")
    print(f"Whisper Model: {whisper_model_size}")
    print(f"Settings: No VAD, No voice filter, No Demucs separation")
    
    try:
        # Import and initialize lyrics extractor directly (no database needed)
        from src.rag.lyrics_extractor import LyricsExtractor
        import time
        
        print("\n[TIMING] Starting model initialization...")
        init_start = time.time()
        
        print("[TIMING] Importing LyricsExtractor class...")
        print("[TIMING] Creating LyricsExtractor instance...")
        lyrics_extractor = LyricsExtractor(
            whisper_model_size=whisper_model_size,
            use_gpu=True,
            min_confidence=0.5,
            load_demucs=False  # Don't load Demucs for testing
        )
        init_time = time.time() - init_start
        print(f"[TIMING] [OK] Model initialization completed in {init_time:.2f} seconds")
        
        if not lyrics_extractor.is_available():
            print("\n[ERROR] Lyrics extractor not available (missing dependencies)")
            return
        
        print("\n[TIMING] Starting lyrics extraction...")
        extract_start = time.time()
        
        # Extract lyrics without database indexing
        result = lyrics_extractor.extract_lyrics(
            audio_path=str(audio_file),
            separate_vocals=False,
            vad_filter=False,
            vad_min_silence_ms=2000,
            vad_threshold=0.3,
            apply_voice_filter=False
        )
        extract_time = time.time() - extract_start
        print(f"[TIMING] [OK] Lyrics extraction completed in {extract_time:.2f} seconds")
        
        # Display results
        print("\n[TIMING] Preparing results for display...")
        print("\n" + "="*70)
        print("Results")
        print("="*70)
        
        if result.get('error'):
            print(f"\n[ERROR] Extraction failed: {result.get('error', 'Unknown error')}")
        else:
            print(f"\n[OK] Lyrics extracted successfully!")
            print(f"\nConfidence: {result.get('confidence', 0):.1%}")
            print(f"Segments: {result.get('segment_count', 0)}")
            print(f"Characters: {len(result.get('lyrics', ''))}")
            
            # Save lyrics to file for comparison
            output_file = f"lyrics_output_{whisper_model_size}.txt"
            try:
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"Model: {whisper_model_size}\n")
                    f.write(f"Confidence: {result.get('confidence', 0):.1%}\n")
                    f.write(f"Segments: {result.get('segment_count', 0)}\n")
                    f.write(f"Characters: {len(result.get('lyrics', ''))}\n")
                    f.write("="*70 + "\n")
                    f.write(result.get('lyrics', ''))
                print(f"\nLyrics saved to: {output_file}")
            except Exception as e:
                print(f"\nWarning: Could not save lyrics to file: {e}")
        
        print("\n[TIMING] Cleaning up resources...")
        cleanup_start = time.time()
        del lyrics_extractor
        
        # Force GPU memory cleanup
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
        except:
            pass
            
        cleanup_time = time.time() - cleanup_start
        print(f"[TIMING] [OK] Cleanup completed in {cleanup_time:.2f} seconds")
        print(f"[TIMING] Total time: {init_time + extract_time + cleanup_time:.2f} seconds")
        
    except Exception as e:
        print(f"\n[ERROR] Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract and index lyrics from audio files')
    parser.add_argument('--audio-library', default='audio_library', help='Path to audio library')
    parser.add_argument('--max-songs', type=int, help='Maximum number of songs to process')
    parser.add_argument('--vocal-separation', action='store_true', help='Enable vocal separation (slow but cleaner)')
    parser.add_argument('--min-confidence', type=float, default=0.5, help='Minimum transcription confidence (0-1)')
    parser.add_argument('--reindex', action='store_true', help='Reindex songs that already have lyrics')
    parser.add_argument('--test', help='Test on a single audio file')
    parser.add_argument('--status', action='store_true', help='Check lyrics indexing status')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt for batch processing')
    parser.add_argument('--vad', action='store_true', help='Enable voice activity detection filtering')
    parser.add_argument('--vad-silence', type=int, default=2000, help='Min silence duration in ms for VAD filtering (default 2000 = 2 seconds)')
    parser.add_argument('--vad-threshold', type=float, default=0.3, help='VAD threshold 0.0-1.0, lower=more sensitive (default 0.3)')
    parser.add_argument('--voice-filter', action='store_true', help='Apply voice frequency bandpass filter (80-8000 Hz)')
    parser.add_argument('--whisper-model', default='large-v3', 
                       choices=['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3'],
                       help='Whisper model size (default: large-v3, most accurate)')
    
    args = parser.parse_args()
    
    if args.test:
        await test_single_song(args.test, whisper_model_size=args.whisper_model)
        print("\n[TIMING] Test completed successfully")
        return  # Exit cleanly
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
            separate_vocals=args.vocal_separation,
            min_confidence=args.min_confidence,
            reindex=args.reindex,
            skip_confirmation=args.yes,
            vad_filter=args.vad,
            vad_min_silence_ms=args.vad_silence,
            vad_threshold=args.vad_threshold,
            apply_voice_filter=args.voice_filter,
            whisper_model_size=args.whisper_model
        )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        # Ensure GPU resources are fully released before exit
        try:
            import torch
            import gc
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
        except:
            pass
