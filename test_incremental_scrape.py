"""
Test the incremental scraping with database skip logic
"""

import logging
import asyncio
from web_scraper import BigFlavorScraper
from database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Test incremental scraping."""
    
    print("\n" + "="*60)
    print("Testing Incremental Scraping with Database Skip")
    print("="*60 + "\n")
    
    # Connect to database
    print("Connecting to database...")
    db = DatabaseManager()
    await db.connect()
    
    # Get existing song IDs
    existing_song_ids = await db.get_all_song_ids()
    print(f"Loaded {len(existing_song_ids)} existing song IDs from database")
    print(f"Sample IDs: {list(existing_song_ids)[:5]}\n")
    
    scraper = None
    
    try:
        # Initialize scraper
        print("Initializing scraper...")
        scraper = BigFlavorScraper(
            headless=False,  # Visible for testing
            download_audio=True
        )
        
        # Navigate to songs page
        print("Navigating to songs page...")
        scraper.navigate_to_songs()
        
        # Scrape just 10 songs to test
        print("\nScraping 10 songs (should skip existing ones)...")
        songs = scraper.get_all_songs_with_details(
            max_scrolls=5,
            limit=10,
            existing_song_ids=existing_song_ids
        )
        
        new_songs = [s for s in songs if not s.get('skipped')]
        skipped_songs = [s for s in songs if s.get('skipped')]
        
        print(f"\n✓ Results:")
        print(f"  Total processed: {len(songs)}")
        print(f"  New songs: {len(new_songs)}")
        print(f"  Skipped (already in DB): {len(skipped_songs)}")
        
        if skipped_songs:
            print(f"\nSkipped songs:")
            for song in skipped_songs[:5]:
                print(f"  - {song['title']}")
        
        if new_songs:
            print(f"\nNew songs to save:")
            for song in new_songs[:5]:
                print(f"  - {song['title']}")
        
    finally:
        if scraper:
            scraper.stop()
        
        await db.close()
    
    print("\nTest complete! Press Enter to exit...")
    input()


if __name__ == "__main__":
    asyncio.run(main())
