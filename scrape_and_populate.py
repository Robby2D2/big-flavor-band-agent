"""
Script to scrape Big Flavor Band website and populate the database
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional

from web_scraper import BigFlavorScraper
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager


# Configure logging
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


async def run_scraper(
    db: DatabaseManager,
    username: Optional[str] = None,
    password: Optional[str] = None,
    headless: bool = True,
    download_audio: bool = True
):
    """
    Run the web scraper and populate database
    
    Args:
        db: DatabaseManager instance
        username: Login username (if required)
        password: Login password (if required)
        headless: Run browser in headless mode
        download_audio: Download MP3 files
    """
    # Create scraped data manager
    scraper_db = ScrapedDataManager(db)
    
    # Start scraping
    logger.info("Starting web scraper...")
    
    with BigFlavorScraper(headless=headless, download_audio=download_audio) as scraper:
        # Login if credentials provided
        if username and password:
            logger.info("Logging in...")
            if not scraper.login(username, password):
                logger.error("Login failed")
                return
        
        # Scrape all songs
        logger.info("Scraping all songs...")
        songs = scraper.scrape_all_songs()
        
        logger.info(f"Scraped {len(songs)} songs. Inserting into database...")
        
        # Insert songs into database
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
            recorded_on = datetime.strptime(scraped_song['recorded_on'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    
    uploaded_on = None
    if scraped_song.get('uploaded_on'):
        try:
            uploaded_on = datetime.strptime(scraped_song['uploaded_on'], '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            try:
                uploaded_on = datetime.strptime(scraped_song['uploaded_on'], '%Y-%m-%d')
            except (ValueError, TypeError):
                pass
    
    # Prepare song data
    song_data = {
        'id': scraped_song.get('id', ''),
        'title': scraped_song.get('title', ''),
        'session': scraped_song.get('session'),
        'rating': scraped_song.get('rating'),
        'is_original': scraped_song.get('is_original', False),
        'recorded_on': recorded_on,
        'uploaded_on': uploaded_on,
        'track_number': scraped_song.get('track_number'),
        'audio_url': scraped_song.get('audio_url'),
        'genre': scraped_song.get('genre'),
        'tempo_bpm': scraped_song.get('tempo_bpm'),
        'key': scraped_song.get('key'),
        'duration_seconds': scraped_song.get('duration_seconds'),
        'energy': scraped_song.get('energy'),
        'mood': scraped_song.get('mood'),
        'audio_quality': scraped_song.get('audio_quality'),
        'comments': scraped_song.get('comments', []),
        'instruments': scraped_song.get('instruments', [])
    }
    
    # Use local audio path if available
    if scraped_song.get('local_audio_path'):
        song_data['audio_url'] = scraped_song['local_audio_path']
    
    return song_data


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Scrape Big Flavor Band website')
    parser.add_argument('--username', '-u', help='Login username (if required)')
    parser.add_argument('--password', '-p', help='Login password (if required)')
    parser.add_argument('--no-headless', action='store_true', help='Show browser window')
    parser.add_argument('--no-download', action='store_true', help='Skip downloading audio files')
    
    args = parser.parse_args()
    
    # Setup database
    db = await setup_database()
    
    try:
        # Run scraper
        await run_scraper(
            db,
            username=args.username,
            password=args.password,
            headless=not args.no_headless,
            download_audio=not args.no_download
        )
    finally:
        # Cleanup
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
