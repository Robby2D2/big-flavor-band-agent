"""
Scrape all songs from bigflavorband.com and load into database
This will:
1. Scrape all songs with full details (one at a time)
2. Download MP3 files to audio_library
3. Insert all data into PostgreSQL database
"""

import asyncio
import logging
import json
import re
from datetime import datetime
from web_scraper import BigFlavorScraper
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

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
    print()
    
    # Ask for confirmation
    response = input("This may take 30+ minutes. Continue? (yes/no): ").strip().lower()
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
        
        # Initialize scraper
        print("\n[2/4] Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=False,  # Visible browser so you can watch progress
            download_audio=True  # Download MP3 files
        )
        scraper.navigate_to_songs()
        print("✓ Scraper initialized")
        
        # Scrape all songs
        print("\n[3/4] Scraping all songs with details...")
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
        print(f"\n[4/4] Loading {len(songs)} songs into database...")
        
        inserted_count = 0
        error_count = 0
        
        for i, song_data in enumerate(songs, 1):
            try:
                # Generate an ID from the title if not present
                if 'id' not in song_data:
                    # Create a simple ID from the title
                    song_id = re.sub(r'[^a-z0-9]+', '_', song_data.get('title', f'song_{i}').lower()).strip('_')
                    song_data['id'] = song_id[:50]  # Limit length
                
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
        
        # Summary
        print("\n" + "="*70)
        print("SCRAPING COMPLETE!")
        print("="*70)
        print(f"Songs scraped:     {len(songs)}")
        print(f"Songs in database: {inserted_count}")
        print(f"Errors:            {error_count}")
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
