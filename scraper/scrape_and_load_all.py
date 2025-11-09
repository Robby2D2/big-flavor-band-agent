"""
Scrape all songs from bigflavorband.com and load into database
This will:
1. Scrape all songs with full details (one at a time)
2. Download MP3 files to audio_library
3. Insert all data into PostgreSQL database
4. Extract lyrics using Whisper v3-large model
5. Index songs in RAG system for semantic search
"""

import asyncio
import logging
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from web_scraper import BigFlavorScraper
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

# Add project root to path for RAG imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.rag.big_flavor_rag import SongRAGSystem

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Main scraping and loading process"""
    
    print("\n" + "="*70)
    print("Big Flavor Band - Full Scrape and Database Load")
    print("="*70)
    print("\nThis will:")
    print("  1. Scrape ALL songs from bigflavorband.com")
    print("  2. Extract full details from each song's Edit page")
    print("  3. Download MP3 files to audio_library/")
    print("  4. Load all data into PostgreSQL database")
    print("  5. Extract lyrics using Whisper v3-large model")
    print("  6. Index songs in RAG system for semantic search")
    print()
    
    # Ask for confirmation
    response = input("This may take 60+ minutes. Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    scraper = None
    db_manager = None
    
    try:
        # Initialize database
        print("\n[1/6] Connecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Initialize RAG system
        print("\n[2/6] Initializing RAG system...")
        rag_system = SongRAGSystem(db_manager, use_clap=True)
        print("✓ RAG system initialized")
        
        # Initialize scraper
        print("\n[3/6] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=False,  # Visible browser so you can watch progress
            download_audio=True  # Download MP3 files
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape all songs
        print("\n[4/6] Scraping all songs with details...")
        print("(This is the slow part - watch the browser!)")
        print()
        
        start_time = datetime.now()
        songs = scraper.get_all_songs_with_details(
            max_scrolls=1000,  # Very high limit to get all songs
            limit=None  # No limit on number of songs
        )
        
        scrape_duration = datetime.now() - start_time
        print(f"\n✓ Scraped {len(songs)} songs in {scrape_duration}")
        
        # Save raw scraped data as backup
        backup_file = f"scraped_songs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w') as f:
            json.dump(songs, f, indent=2, default=str)
        print(f"✓ Saved backup to {backup_file}")
        
        # Load into database
        print(f"\n[5/6] Loading {len(songs)} songs into database...")
        
        inserted_count = 0
        error_count = 0
        
        for i, song_data in enumerate(songs, 1):
            try:
                # Ensure song has numeric ID from audio URL
                if 'id' not in song_data or not song_data['id']:
                    logger.warning(f"Song {i} missing ID, skipping: {song_data.get('title', 'Unknown')}")
                    error_count += 1
                    continue
                
                song_id = await data_manager.insert_song_with_details(song_data)
                inserted_count += 1
                
                if i % 10 == 0:
                    print(f"  Loaded {i}/{len(songs)} songs...")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Failed to insert song {song_data.get('title', 'unknown')}: {e}")
        
        print(f"\n✓ Loaded {inserted_count} songs into database")
        if error_count > 0:
            print(f"  ⚠ {error_count} songs failed to load (see errors above)")
        
        # Extract lyrics and index in RAG system
        print(f"\n[6/6] Extracting lyrics and indexing in RAG system...")
        print("(This will use Whisper v3-large - may take a while)")
        print()
        
        lyrics_success = 0
        lyrics_error = 0
        
        for i, song_data in enumerate(songs, 1):
            if 'local_audio_path' not in song_data or not song_data['local_audio_path']:
                logger.debug(f"Skipping lyrics extraction for song {song_data.get('id')} - no local audio")
                continue
            
            try:
                audio_path = song_data['local_audio_path']
                song_id = song_data['id']
                
                print(f"  [{i}/{len(songs)}] Extracting lyrics: {song_data.get('title', 'Unknown')[:50]}...")
                
                # Extract and index lyrics with RAG
                result = await rag_system.extract_and_index_lyrics(
                    audio_path=audio_path,
                    song_id=song_id,
                    separate_vocals=False,  # Don't separate vocals (faster)
                    vad_filter=True,  # Use voice activity detection
                    vad_min_silence_ms=2000,
                    apply_voice_filter=False,
                    whisper_model_size='large-v3'  # Use v3-large as requested
                )
                
                if result.get('lyrics'):
                    lyrics_success += 1
                    logger.info(f"  ✓ Extracted {len(result['lyrics'])} characters of lyrics")
                else:
                    lyrics_error += 1
                    logger.warning(f"  ⚠ No lyrics extracted")
                    
            except Exception as e:
                lyrics_error += 1
                logger.error(f"Failed to extract lyrics for song {song_data.get('id')}: {e}")
        
        print(f"\n✓ Lyrics extraction complete")
        print(f"  Success: {lyrics_success}")
        print(f"  Failed:  {lyrics_error}")
        
        # Summary
        print("\n" + "="*70)
        print("SCRAPING COMPLETE!")
        print("="*70)
        print(f"Songs scraped:     {len(songs)}")
        print(f"Songs in database: {inserted_count}")
        print(f"Lyrics extracted:  {lyrics_success}")
        print(f"Errors:            {error_count + lyrics_error}")
        print(f"Duration:          {scrape_duration}")
        print(f"Backup file:       {backup_file}")
        print()
        
        # Show some stats
        sessions = set(s.get('session') for s in songs if s.get('session'))
        musicians = set()
        for song in songs:
            for inst in song.get('instruments', []):
                if inst.get('musician'):
                    musicians.add(inst['musician'])
        
        print(f"Unique sessions:   {len(sessions)}")
        print(f"Unique musicians:  {len(musicians)}")
        print()
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        # Cleanup
        if scraper:
            print("\nClosing browser...")
            scraper.stop()
        
        if db_manager:
            print("Closing database connection...")
            await db_manager.close()
        
        print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
