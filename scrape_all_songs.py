"""
Scrape all songs from bigflavorband.com and save to database.
This version checks the database first and skips songs we already have.
"""

import logging
import asyncio
import json
import sys
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
    """Main scraping function with database integration."""
    
    print("\n" + "="*60)
    print("Big Flavor Band - Complete Song Database Scraper")
    print("="*60 + "\n")
    
    # Connect to database first
    print("Connecting to database...")
    db = DatabaseManager()
    await db.connect()
    
    # Get existing song IDs
    print("Loading existing songs from database...")
    existing_song_ids = await db.get_all_song_ids()
    print(f"Found {len(existing_song_ids)} songs already in database\n")
    
    scraper = None
    data_manager = None
    
    try:
        # Initialize scraper
        print("Initializing web scraper...")
        scraper = BigFlavorScraper(
            headless=False,  # Run visible for debugging scroll issues
            download_audio=True  # Download MP3 files
        )
        
        # Initialize data manager
        data_manager = ScrapedDataManager(db)
        
        # Navigate to songs page
        print("Navigating to songs page...")
        scraper.navigate_to_songs()
        
        # Scrape all songs with details, skipping ones we already have
        print("\nStarting scrape...")
        print("This will:")
        print("- Skip songs already in database")
        print("- Click into new songs to get full details")
        print("- Download MP3 files")
        print("- Save to database as we go")
        print()
        
        songs = scraper.get_all_songs_with_details(
            max_scrolls=999,  # Large number to keep scrolling until we hit the end
            limit=None,  # Get all songs
            existing_song_ids=existing_song_ids  # Skip these
        )
        
        new_songs_count = len([s for s in songs if not s.get('skipped')])
        skipped_count = len([s for s in songs if s.get('skipped')])
        
        print(f"\n✓ Scraping complete!")
        print(f"  New songs scraped: {new_songs_count}")
        print(f"  Songs skipped (already in DB): {skipped_count}")
        print(f"  Total songs processed: {len(songs)}")
        
        # Filter out skipped songs before saving
        new_songs = [s for s in songs if not s.get('skipped')]
        
        if new_songs:
            # Save to backup file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = f"scraped_songs_{timestamp}.json"
            
            print(f"\nSaving backup to: {backup_file}")
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(new_songs, f, indent=2, ensure_ascii=False)
            
            # Save to database
            print(f"\nSaving {len(new_songs)} new songs to database...")
            saved_count = 0
            failed_count = 0
            
            for i, song in enumerate(new_songs, 1):
                try:
                    await data_manager.insert_song_with_details(song)
                    saved_count += 1
                    if i % 10 == 0:
                        print(f"  Saved {i}/{len(new_songs)} songs...")
                except Exception as e:
                    logger.error(f"Failed to save song '{song.get('title', 'unknown')}': {e}")
                    failed_count += 1
            
            print(f"\n✓ Database save complete!")
            print(f"  Successfully saved: {saved_count}")
            print(f"  Failed: {failed_count}")
        else:
            print("\nNo new songs to save - all songs already in database!")
        
        # Show final stats
        all_song_ids = await db.get_all_song_ids()
        print(f"\nTotal songs now in database: {len(all_song_ids)}")
        
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
        sys.exit(1)
    
    except Exception as e:
        logger.error(f"Error during scraping: {e}", exc_info=True)
        raise
    
    finally:
        # Clean up
        if scraper:
            scraper.stop()
        
        if db:
            await db.close()
    
    print("\n" + "="*60)
    print("Scraping complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
