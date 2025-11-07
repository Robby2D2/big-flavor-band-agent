"""
Example of using the database with PostgreSQL and pgvector
"""

import asyncio
from database import DatabaseManager


async def main():
    # Initialize database
    db = DatabaseManager()
    await db.connect()
    
    try:
        # Insert a song
        song = {
            'id': 'song_001',
            'title': 'Summer Groove',
            'genre': 'Rock',
            'tempo_bpm': 128.0,
            'key': 'C Major',
            'duration_seconds': 245,
            'energy': 'high',
            'mood': 'upbeat',
            'audio_quality': 'good',
            'audio_url': 'https://example.com/song.mp3'
        }
        
        await db.insert_song(song)
        
        # Get all songs
        songs = await db.get_all_songs()
        print(f"Found {len(songs)} songs")
        
        # Search songs
        rock_songs = await db.search_songs(genre='Rock')
        print(f"Found {len(rock_songs)} rock songs")
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
