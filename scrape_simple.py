"""
Simple scraper - extracts data available from the main table
This version doesn't require clicking into detail pages
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional

from web_scraper import BigFlavorScraper
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraping.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def setup_database():
    """Initialize database connection"""
    db = DatabaseManager(
        host="localhost",
        port=5432,
        database="bigflavor",
        user="bigflavor",
        password="bigflavor_dev_pass"
    )
    await db.connect()
    return db


def prepare_song_data(scraped_song: dict) -> dict:
    """
    Prepare scraped song data for database insertion
    
    Args:
        scraped_song: Raw scraped song data
        
    Returns:
        Formatted song data
    """
    # Convert dates
    recorded_on = None
    if scraped_song.get('recorded_on'):
        try:
            recorded_on = datetime.strptime(scraped_song['recorded_on'], '%b %d, %Y').date()
        except (ValueError, TypeError):
            pass
    
    uploaded_on = None
    if scraped_song.get('uploaded_on'):
        try:
            uploaded_on = datetime.strptime(scraped_song['uploaded_on'], '%b %d, %Y')
        except (ValueError, TypeError):
            pass
    
    # Prepare song data
    song_data = {
        'id': scraped_song.get('id', ''),
        'title': scraped_song.get('title', ''),
        'session': scraped_song.get('session'),
        'rating': scraped_song.get('rating'),
        'recorded_on': recorded_on,
        'uploaded_on': uploaded_on,
        'comments': scraped_song.get('comments', [])
    }
    
    return song_data


async def run_simple_scraper(db: DatabaseManager):
    """
    Run the simple web scraper (main table only)
    
    Args:
        db: DatabaseManager instance
    """
    scraper_db = ScrapedDataManager(db)
    
    logger.info("Starting simple web scraper (main table only)...")
    
    with BigFlavorScraper(headless=False, download_audio=False) as scraper:
        # Scrape song list
        logger.info("Scraping song list...")
        songs = scraper.get_all_songs()
        
        logger.info(f"Scraped {len(songs)} songs. Inserting into database...")
        
        success_count = 0
        error_count = 0
        
        for i, song in enumerate(songs, 1):
            try:
                logger.info(f"Inserting song {i}/{len(songs)}: {song.get('title', 'Unknown')}")
                
                # Prepare song data for database
                song_data = prepare_song_data(song)
                
                # Insert with all details
                await scraper_db.insert_song_with_details(song_data)
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Error inserting song {song.get('id', 'unknown')}: {e}")
                error_count += 1
                continue
        
        logger.info(f"Scraping complete! Success: {success_count}, Errors: {error_count}")
        
        # Save scraped data to JSON for backup
        output_file = f"scraped_songs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(songs, indent=2, fp=f, default=str)
        logger.info(f"Backup saved to {output_file}")


async def main():
    """Main entry point"""
    # Setup database
    db = await setup_database()
    
    try:
        # Run scraper
        await run_simple_scraper(db)
    finally:
        # Cleanup
        await db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Simple Big Flavor Band Scraper")
    print("=" * 60)
    print("\nThis will scrape the main song table and insert:")
    print("  - Song titles")
    print("  - Ratings")
    print("  - Sessions")
    print("  - Comments")
    print("  - Dates (recorded, uploaded, updated)")
    print("\nNote: Instruments, original flag, and MP3s require")
    print("      clicking into each song (not included in this version)")
    print("=" * 60)
    
    input("\nPress ENTER to start scraping...")
    
    asyncio.run(main())
