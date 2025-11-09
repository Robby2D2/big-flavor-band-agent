"""
Query database to verify stored songs and lyrics
This script queries the database to show:
1. All songs in the database
2. Songs with lyrics
3. RAG embeddings
4. Example queries for finding songs by performer/instrument
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.database import DatabaseManager


async def main():
    """Query and display database contents"""
    
    print("\n" + "="*70)
    print("Database Verification Query")
    print("="*70)
    print()
    
    db_manager = DatabaseManager()
    
    try:
        await db_manager.connect()
        print("✓ Connected to database")
        print()
        
        # Get all songs
        print("[1] All Songs in Database")
        print("-" * 70)
        
        query = """
            SELECT id, title, session, recorded_on, audio_url
            FROM songs
            ORDER BY id
            LIMIT 50
        """
        
        async with db_manager.pool.acquire() as conn:
            songs = await conn.fetch(query)
        
        print(f"Total songs: {len(songs)}")
        print()
        
        for i, song in enumerate(songs[:10], 1):
            print(f"{i}. ID={song['id']}, Title={song['title']}")
            print(f"   Session={song['session']}, Recorded={song['recorded_on']}")
            if song['audio_url']:
                print(f"   URL={song['audio_url'][:70]}...")
            print()
        
        if len(songs) > 10:
            print(f"... and {len(songs) - 10} more songs")
            print()
        
        # Get songs with lyrics
        print("\n[2] Songs with Lyrics Extracted")
        print("-" * 70)
        
        query = """
            SELECT s.id, s.title, t.content
            FROM songs s
            JOIN text_embeddings t ON s.id = t.song_id
            WHERE t.content_type = 'lyrics'
            ORDER BY s.id
            LIMIT 10
        """
        
        async with db_manager.pool.acquire() as conn:
            songs_with_lyrics = await conn.fetch(query)
        
        print(f"Songs with lyrics: {len(songs_with_lyrics)}")
        print()
        
        for i, song in enumerate(songs_with_lyrics, 1):
            lyrics_preview = song['content'][:150].replace('\n', ' ').strip()
            print(f"{i}. ID={song['id']}, Title={song['title']}")
            print(f"   Lyrics ({len(song['content'])} chars): {lyrics_preview}...")
            print()
        
        # Get RAG embeddings count
        print("\n[3] RAG System Embeddings")
        print("-" * 70)
        
        queries = [
            ("Text embeddings (lyrics, metadata)", "SELECT COUNT(*) FROM text_embeddings"),
            ("Audio embeddings", "SELECT COUNT(*) FROM audio_embeddings"),
            ("Song embeddings", "SELECT COUNT(*) FROM song_embeddings"),
        ]
        
        for label, query in queries:
            async with db_manager.pool.acquire() as conn:
                count = await conn.fetchval(query)
            print(f"{label}: {count}")
        
        print()
        
        # Example query: Find songs by musician
        print("\n[4] Example Query: Find songs by Rob Danek on Lead Vocals")
        print("-" * 70)
        
        query = """
            SELECT DISTINCT s.id, s.title, s.session
            FROM songs s
            JOIN song_instruments si ON s.id = si.song_id
            JOIN musicians m ON si.musician_id = m.id
            JOIN instruments i ON si.instrument_id = i.id
            WHERE m.name = 'Rob Danek' AND i.name LIKE '%Vocals (Lead)%'
            ORDER BY s.title
            LIMIT 10
        """
        
        async with db_manager.pool.acquire() as conn:
            rob_songs = await conn.fetch(query)
        
        print(f"Found {len(rob_songs)} songs with Rob Danek on Lead Vocals:")
        print()
        
        for i, song in enumerate(rob_songs, 1):
            print(f"{i}. {song['title']} (Session: {song['session']})")
        
        if not rob_songs:
            print("(No songs found - try scraping more songs or check musician names)")
        
        print()
        
        # Show all musicians
        print("\n[5] All Musicians in Database")
        print("-" * 70)
        
        query = """
            SELECT name, COUNT(DISTINCT si.song_id) as song_count
            FROM musicians m
            LEFT JOIN song_instruments si ON m.id = si.musician_id
            GROUP BY m.name
            ORDER BY song_count DESC, name
            LIMIT 20
        """
        
        async with db_manager.pool.acquire() as conn:
            musicians = await conn.fetch(query)
        
        print(f"Total musicians: {len(musicians)}")
        print()
        
        for i, musician in enumerate(musicians, 1):
            print(f"{i}. {musician['name']}: {musician['song_count']} songs")
        
        print()
        
        # Show comments
        print("\n[6] Sample Comments")
        print("-" * 70)
        
        query = """
            SELECT s.title, sc.comment_text, sc.author
            FROM song_comments sc
            JOIN songs s ON sc.song_id = s.id
            LIMIT 10
        """
        
        async with db_manager.pool.acquire() as conn:
            comments = await conn.fetch(query)
        
        print(f"Total comments found: {len(comments)}")
        print()
        
        for i, comment in enumerate(comments, 1):
            print(f"{i}. {comment['title']}")
            print(f"   Author: {comment['author']}")
            print(f"   Comment: {comment['comment_text'][:100]}...")
            print()
        
        if not comments:
            print("(No comments found - make sure comments are being scraped)")
            print()
        
        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        
        async with db_manager.pool.acquire() as conn:
            total_songs = await conn.fetchval("SELECT COUNT(*) FROM songs")
            total_lyrics = await conn.fetchval("SELECT COUNT(*) FROM text_embeddings WHERE content_type = 'lyrics'")
            total_comments = await conn.fetchval("SELECT COUNT(*) FROM song_comments")
            total_instruments = await conn.fetchval("SELECT COUNT(*) FROM song_instruments")
            total_musicians = await conn.fetchval("SELECT COUNT(*) FROM musicians")
        
        print(f"Total songs:        {total_songs}")
        print(f"Songs with lyrics:  {total_lyrics}")
        print(f"Total comments:     {total_comments}")
        print(f"Instrument entries: {total_instruments}")
        print(f"Unique musicians:   {total_musicians}")
        print()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db_manager.close()
        print("✓ Database connection closed")
        print()


if __name__ == "__main__":
    asyncio.run(main())
