"""
Load scraped songs from JSON backup file into database
"""

import asyncio
import logging
import json
import re
import sys
from database import DatabaseManager
from scraped_data_manager import ScrapedDataManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Load songs from backup file into database"""
    
    if len(sys.argv) < 2:
        print("Usage: python load_from_backup.py <backup_file.json>")
        print("\nExample: python load_from_backup.py scraped_songs_20251106_135207.json")
        return
    
    backup_file = sys.argv[1]
    
    print(f"\nLoading songs from: {backup_file}")
    
    # Load songs from JSON
    with open(backup_file, 'r') as f:
        songs = json.load(f)
    
    print(f"Found {len(songs)} songs in backup file")
    
    db_manager = None
    
    try:
        # Initialize database
        print("\nConnecting to database...")
        db_manager = DatabaseManager()
        await db_manager.connect()
        data_manager = ScrapedDataManager(db_manager)
        print("✓ Database connected")
        
        # Load into database
        print(f"\nLoading {len(songs)} songs into database...")
        
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
        
        # Show some stats
        sessions = set(s.get('session') for s in songs if s.get('session'))
        musicians = set()
        for song in songs:
            for inst in song.get('instruments', []):
                if inst.get('musician'):
                    musicians.add(inst['musician'])
        
        print(f"\nDatabase loaded successfully!")
        print(f"Songs:             {inserted_count}")
        print(f"Unique sessions:   {len(sessions)}")
        print(f"Unique musicians:  {len(musicians)}")
        
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        
    finally:
        if db_manager:
            print("\nClosing database connection...")
            await db_manager.close()
        
        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
