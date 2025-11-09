"""
Extended database operations for web-scraped song data
Handles comments, instruments, musicians, and sessions
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ScrapedDataManager:
    """Manage scraped song data in the database"""
    
    def __init__(self, db_manager):
        """
        Initialize with a DatabaseManager instance
        
        Args:
            db_manager: DatabaseManager instance with active connection pool
        """
        self.db = db_manager
    
    async def insert_song_with_details(self, song_data: Dict[str, Any]) -> int:
        """
        Insert a song with all scraped details
        
        Args:
            song_data: Complete song data from scraper
            
        Returns:
            Song ID (integer)
        """
        # Ensure song ID is an integer
        if 'id' in song_data:
            if isinstance(song_data['id'], str):
                try:
                    song_data['id'] = int(song_data['id'])
                except ValueError:
                    raise ValueError(f"Song ID must be numeric, got: {song_data['id']}")
        
        # Insert basic song data
        song_id = await self.db.insert_song(song_data)
        
        # Insert session if provided
        if song_data.get('session'):
            await self.insert_session(song_data['session'])
        
        # Insert comments
        if song_data.get('comments'):
            for comment in song_data['comments']:
                await self.insert_comment(
                    song_id,
                    comment.get('text', ''),
                    comment.get('author')
                )
        
        # Insert instruments and musicians
        if song_data.get('instruments'):
            for instrument_data in song_data['instruments']:
                await self.insert_song_instrument(
                    song_id,
                    instrument_data.get('musician', ''),
                    instrument_data.get('instrument', '')
                )
        
        logger.info(f"Inserted song with all details: {song_id}")
        return song_id
    
    async def insert_session(self, session_name: str, description: str = None) -> int:
        """Insert or get a session"""
        query = """
            INSERT INTO sessions (name, description)
            VALUES ($1, $2)
            ON CONFLICT (name) DO UPDATE SET
                description = COALESCE(EXCLUDED.description, sessions.description)
            RETURNING id
        """
        
        async with self.db.pool.acquire() as conn:
            session_id = await conn.fetchval(query, session_name, description)
        
        return session_id
    
    async def insert_comment(
        self,
        song_id: int,
        comment_text: str,
        author: str = None
    ) -> int:
        """Insert a comment for a song"""
        query = """
            INSERT INTO song_comments (song_id, comment_text, author)
            VALUES ($1, $2, $3)
            RETURNING id
        """
        
        async with self.db.pool.acquire() as conn:
            comment_id = await conn.fetchval(query, song_id, comment_text, author)
        
        logger.debug(f"Inserted comment for song {song_id}")
        return comment_id
    
    async def get_song_comments(self, song_id: int) -> List[Dict[str, Any]]:
        """Get all comments for a song"""
        query = """
            SELECT id, comment_text, author, created_at, updated_at
            FROM song_comments
            WHERE song_id = $1
            ORDER BY created_at DESC
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, song_id)
        
        return [dict(row) for row in rows]
    
    async def insert_musician(self, musician_name: str) -> int:
        """Insert or get a musician"""
        query = """
            INSERT INTO musicians (name)
            VALUES ($1)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """
        
        async with self.db.pool.acquire() as conn:
            musician_id = await conn.fetchval(query, musician_name)
        
        return musician_id
    
    async def insert_instrument(self, instrument_name: str) -> int:
        """Insert or get an instrument"""
        query = """
            INSERT INTO instruments (name)
            VALUES ($1)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
        """
        
        async with self.db.pool.acquire() as conn:
            instrument_id = await conn.fetchval(query, instrument_name)
        
        return instrument_id
    
    async def insert_song_instrument(
        self,
        song_id: int,
        musician_name: str,
        instrument_name: str
    ) -> int:
        """Link a song with a musician and instrument"""
        # Get or create musician and instrument
        musician_id = await self.insert_musician(musician_name)
        instrument_id = await self.insert_instrument(instrument_name)
        
        query = """
            INSERT INTO song_instruments (song_id, musician_id, instrument_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (song_id, musician_id, instrument_id) DO NOTHING
            RETURNING id
        """
        
        async with self.db.pool.acquire() as conn:
            result = await conn.fetchval(query, song_id, musician_id, instrument_id)
        
        if result:
            logger.debug(f"Linked song {song_id} with {musician_name} on {instrument_name}")
        
        return result if result else 0
    
    async def get_song_instruments(self, song_id: int) -> List[Dict[str, Any]]:
        """Get all instruments and musicians for a song"""
        query = """
            SELECT 
                m.name as musician,
                i.name as instrument
            FROM song_instruments si
            JOIN musicians m ON si.musician_id = m.id
            JOIN instruments i ON si.instrument_id = i.id
            WHERE si.song_id = $1
            ORDER BY m.name, i.name
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, song_id)
        
        return [dict(row) for row in rows]
    
    async def get_musician_songs(self, musician_name: str) -> List[Dict[str, Any]]:
        """Get all songs a musician played on"""
        query = """
            SELECT 
                s.id,
                s.title,
                s.session,
                i.name as instrument
            FROM songs s
            JOIN song_instruments si ON s.id = si.song_id
            JOIN musicians m ON si.musician_id = m.id
            JOIN instruments i ON si.instrument_id = i.id
            WHERE m.name = $1
            ORDER BY s.title
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, musician_name)
        
        return [dict(row) for row in rows]
    
    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all recording sessions"""
        query = """
            SELECT 
                s.id,
                s.name,
                s.description,
                COUNT(songs.id) as song_count
            FROM sessions s
            LEFT JOIN songs ON songs.session = s.name
            GROUP BY s.id, s.name, s.description
            ORDER BY s.name
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
    
    async def get_session_songs(self, session_name: str) -> List[Dict[str, Any]]:
        """Get all songs from a session"""
        query = """
            SELECT *
            FROM songs
            WHERE session = $1
            ORDER BY track_number, title
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, session_name)
        
        return [dict(row) for row in rows]
    
    async def update_song_rating(self, song_id: str, rating: int) -> bool:
        """Update a song's rating"""
        query = """
            UPDATE songs
            SET rating = $2, updated_at = CURRENT_TIMESTAMP
            WHERE id = $1
        """
        
        async with self.db.pool.acquire() as conn:
            result = await conn.execute(query, song_id, rating)
        
        return result == "UPDATE 1"
    
    async def get_top_rated_songs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top rated songs"""
        query = """
            SELECT *
            FROM songs
            WHERE rating IS NOT NULL
            ORDER BY rating DESC, title
            LIMIT $1
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
        
        return [dict(row) for row in rows]
    
    async def get_original_songs(self) -> List[Dict[str, Any]]:
        """Get all original songs"""
        query = """
            SELECT *
            FROM songs
            WHERE is_original = TRUE
            ORDER BY title
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
