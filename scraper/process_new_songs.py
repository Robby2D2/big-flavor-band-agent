"""
Process ONLY NEW/UPDATED songs from bigflavorband.com
Sorts by "Updated" date and processes only songs newer than latest in database.

Usage:
  python process_new_songs.py          # Process new songs only
  python process_new_songs.py --all    # Process all songs (like process_all_songs.py)
"""

import asyncio
import logging
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scraper.web_scraper import BigFlavorScraper
from database.database import DatabaseManager
from scraper.scraped_data_manager import ScrapedDataManager
from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def get_latest_updated_date(db_manager: DatabaseManager):
    """Get the most recent updated_at timestamp from the database"""
    try:
        query = "SELECT MAX(updated_at) FROM songs WHERE updated_at IS NOT NULL"
        latest = await db_manager.pool.fetchval(query)
        return latest
    except Exception as e:
        logger.warning(f"Could not get latest updated date: {e}")
        return None


async def process_song(song_data: dict, db_manager: DatabaseManager, data_manager: ScrapedDataManager, 
                       rag_system: SongRAGSystem, index: int, total: int, lyrics_extractor=None):
    """Process a single song completely"""
    results = {
        'inserted': False,
        'audio_analyzed': False,
        'audio_indexed': False,
        'lyrics_extracted': False,
        'errors': []
    }
    
    try:
        title = song_data.get('title', 'Unknown')
        song_id = song_data.get('id')
        
        print(f"\n{'='*70}")
        print(f"SONG {index}/{total}: {title}")
        print(f"{'='*70}")
        print(f"ID: {song_id}")
        
        if not song_id:
            print("  ✗ Missing song ID")
            results['errors'].append("Missing song ID")
            return results
        
        # 1. Insert into database
        print("\n[1/4] Inserting into database...")
        try:
            inserted_id = await data_manager.insert_song_with_details(song_data)
            results['inserted'] = True
            print(f"  ✓ Inserted song ID {inserted_id}")
        except Exception as e:
            error = f"Database insert error: {e}"
            logger.error(error)
            print(f"  ✗ {error}")
            results['errors'].append(error)
            return results
        
        # Check if audio file exists
        audio_path = song_data.get('local_audio_path')
        if audio_path and Path(audio_path).exists():
            print(f"Audio file: {audio_path}")
            
            # 2. Analyze audio features
            print("\n[2/4] Analyzing audio features...")
            try:
                analysis = rag_system.audio_extractor.analyze_audio(audio_path)
                results['audio_analyzed'] = True
                print(f"  ✓ BPM: {analysis.get('tempo_bpm', 'N/A')}, Key: {analysis.get('key', 'N/A')}, Duration: {analysis.get('duration_seconds', 'N/A')}s")
            except Exception as e:
                error = f"Audio analysis error: {e}"
                logger.error(error)
                print(f"  ✗ {error}")
                results['errors'].append(error)
            
            # 3. Create audio embeddings
            print("\n[3/4] Creating audio embeddings...")
            try:
                result = await rag_system.index_audio_file(audio_path, song_id)
                if result.get('success'):
                    results['audio_indexed'] = True
                    print(f"  ✓ Audio embeddings created")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
            except Exception as e:
                error = f"Audio embedding error: {e}"
                logger.error(error)
                print(f"  ✗ {error}")
                results['errors'].append(error)
            
            # 4. Extract lyrics
            print("\n[4/4] Extracting lyrics (Whisper large-v3)...")
            try:
                result = await rag_system.extract_and_index_lyrics(
                    audio_path=audio_path,
                    song_id=song_id,
                    separate_vocals=False,
                    vad_filter=False,
                    whisper_model_size='large-v3',
                    lyrics_extractor=lyrics_extractor
                )
                
                if result.get('success') and result.get('lyrics'):
                    results['lyrics_extracted'] = True
                    lyrics_len = len(result['lyrics'])
                    confidence = result.get('confidence', 0)
                    print(f"  ✓ Extracted {lyrics_len} characters (confidence: {confidence:.1%})")
                else:
                    error = result.get('error', 'No lyrics extracted')
                    print(f"  ✗ {error}")
                    results['errors'].append(error)
                    
            except Exception as e:
                error = f"Lyrics extraction error: {e}"
                logger.error(error)
                print(f"  ✗ {error}")
                results['errors'].append(error)
        else:
            print("\n  ⚠ No audio file available, skipping analysis and lyrics")
        
        # Summary
        print(f"\n{'─'*70}")
        print(f"SUMMARY: {title[:50]}")
        print(f"  Database: {'✓' if results['inserted'] else '✗'}")
        print(f"  Audio Analysis: {'✓' if results['audio_analyzed'] else '✗'}")
        print(f"  Audio Embeddings: {'✓' if results['audio_indexed'] else '✗'}")
        print(f"  Lyrics: {'✓' if results['lyrics_extracted'] else '✗'}")
        if results['errors']:
            print(f"  Errors: {len(results['errors'])}")
        print(f"{'─'*70}")
        
    except Exception as e:
        error = f"Unexpected error: {e}"
        logger.error(error, exc_info=True)
        results['errors'].append(error)
        print(f"\n✗ ERROR: {error}")
    
    return results


async def main():
    """Main processing function"""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='Process new/updated songs from bigflavorband.com')
    parser.add_argument('--all', action='store_true', help='Process all songs (ignore database dates)')
    args = parser.parse_args()
    
    print("\n" + "="*70)
    if args.all:
        print("Process ALL Songs - Complete Pipeline")
    else:
        print("Process NEW/UPDATED Songs Only")
    print("="*70)
    
    if args.all:
        print("\nThis will:")
        print("  1. Scrape ALL songs from bigflavorband.com")
        print("  2. Process each song completely:")
    else:
        print("\nThis will:")
        print("  1. Sort songs by 'Updated' date (newest first)")
        print("  2. Check database for most recent updated_at timestamp")
        print("  3. Process ONLY songs newer than database")
        print("  4. Stop when reaching already-processed songs")
        print("\n  Each song will be:")
    
    print("     - Inserted/updated in database with metadata")
    print("     - Audio analyzed (BPM, key, duration)")
    print("     - Audio embeddings created")
    print("     - Lyrics extracted (Whisper large-v3)")
    print()
    
    if not args.all:
        print("Note: This is designed for weekly incremental updates.")
        print("      First run will process all songs.")
    
    response = input("\nContinue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    scraper = None
    db_manager = None
    
    try:
        # Initialize database
        print("\n[1/4] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Get latest updated date from database
        latest_date = None
        if not args.all:
            latest_date = await get_latest_updated_date(db_manager)
            if latest_date:
                print(f"✓ Latest song in database: {latest_date}")
            else:
                print("✓ No songs in database yet - will process all")
        
        # Initialize RAG system
        print("\n[2/4] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Initialize scraper
        print("\n[3/4] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=True,
            download_audio=True
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Sort by Updated column if doing incremental
        if not args.all:
            print("\n[4/4] Sorting by 'Updated' date (newest first)...")
            scraper.sort_by_updated_date()
            print("✓ Sorted by updated date")
        else:
            print("\n[4/4] Ready to scrape...")
        
        # Scrape songs
        print("\n" + "="*70)
        if args.all:
            print("COLLECTING ALL SONGS")
        else:
            print("COLLECTING NEW/UPDATED SONGS")
        print("="*70)
        
        if args.all:
            print("\nScraping all songs from website...")
            songs = scraper.get_all_songs_with_details(
                max_scrolls=1000,
                limit=None
            )
        else:
            print("\nScraping songs starting from most recently updated...")
            print("(Will stop when reaching songs already in database)")
            print()
            songs = scraper.get_new_songs_since(
                latest_date=latest_date,
                max_scrolls=1000
            )
        
        if not songs:
            print("\n✓ No new songs to process!")
            return
        
        print(f"✓ Collected {len(songs)} songs to process\n")
        
        # Initialize LyricsExtractor once for reuse
        print("Initializing Whisper large-v3 model (one-time setup)...")
        from src.rag.lyrics_extractor import LyricsExtractor
        lyrics_extractor = LyricsExtractor(
            whisper_model_size='large-v3',
            use_gpu=True,
            min_confidence=0.5,
            load_demucs=False
        )
        print("✓ Whisper model loaded\n")
        
        # Process each song completely
        print("=" * 70)
        print("PROCESSING SONGS ONE AT A TIME")
        print("="*70)
        print()
        
        all_results = []
        for i, song_data in enumerate(songs, 1):
            result = await process_song(
                song_data, 
                db_manager, 
                data_manager, 
                rag_system, 
                i, 
                len(songs),
                lyrics_extractor=lyrics_extractor
            )
            all_results.append(result)
        
        # Final summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        
        total_inserted = sum(1 for r in all_results if r['inserted'])
        total_analyzed = sum(1 for r in all_results if r['audio_analyzed'])
        total_indexed = sum(1 for r in all_results if r['audio_indexed'])
        total_lyrics = sum(1 for r in all_results if r['lyrics_extracted'])
        total_errors = sum(len(r['errors']) for r in all_results)
        
        print(f"\nProcessed {len(all_results)} songs:")
        print(f"  Database inserts:     {total_inserted}/{len(all_results)}")
        print(f"  Audio analysis:       {total_analyzed}/{len(all_results)}")
        print(f"  Audio embeddings:     {total_indexed}/{len(all_results)}")
        print(f"  Lyrics extracted:     {total_lyrics}/{len(all_results)}")
        print(f"  Total errors:         {total_errors}")
        
        if total_errors == 0:
            print("\n✓ All songs processed successfully!")
        else:
            print(f"\n⚠ {total_errors} errors occurred during processing")
        
        print()
        
    except Exception as e:
        logger.error(f"Process failed: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        # Cleanup
        if scraper:
            print("\nClosing browser...")
            scraper.stop()
        
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nProcessing complete!")


if __name__ == "__main__":
    asyncio.run(main())
