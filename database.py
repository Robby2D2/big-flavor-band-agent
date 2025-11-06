"""
Database manager for PostgreSQL with pgvector
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncpg
import json

logger = logging.getLogger("database")


class DatabaseManager:
    """Manage PostgreSQL database connections and operations."""
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "bigflavor",
        user: str = "bigflavor",
        password: str = "bigflavor_dev_pass"
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create database connection pool."""
        self.pool = await asyncpg.create_pool(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            min_size=2,
            max_size=10
        )
        logger.info("Database connection pool created")
    
    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    # Song operations
    async def insert_song(self, song: Dict[str, Any]) -> str:
        """Insert or update a song."""
        query = """
            INSERT INTO songs (
                id, title, genre, tempo_bpm, key, duration_seconds,
                energy, mood, recording_date, audio_quality, audio_url
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (id) DO UPDATE SET
                title = EXCLUDED.title,
                genre = EXCLUDED.genre,
                tempo_bpm = EXCLUDED.tempo_bpm,
                key = EXCLUDED.key,
                duration_seconds = EXCLUDED.duration_seconds,
                energy = EXCLUDED.energy,
                mood = EXCLUDED.mood,
                recording_date = EXCLUDED.recording_date,
                audio_quality = EXCLUDED.audio_quality,
                audio_url = EXCLUDED.audio_url,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            song_id = await conn.fetchval(
                query,
                song['id'],
                song['title'],
                song.get('genre'),
                song.get('tempo_bpm'),
                song.get('key'),
                song.get('duration_seconds'),
                song.get('energy'),
                song.get('mood'),
                song.get('recording_date'),
                song.get('audio_quality'),
                song.get('audio_url')
            )
        
        logger.info(f"Inserted/updated song: {song_id}")
        return song_id
    
    async def get_song(self, song_id: str) -> Optional[Dict[str, Any]]:
        """Get a song by ID."""
        query = "SELECT * FROM songs WHERE id = $1"
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)
        
        return dict(row) if row else None
    
    async def get_all_songs(self) -> List[Dict[str, Any]]:
        """Get all songs."""
        query = "SELECT * FROM songs ORDER BY title"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
    
    async def get_all_song_ids(self) -> set:
        """Get all song IDs in the database."""
        query = "SELECT id FROM songs"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return {row['id'] for row in rows}
    
    async def search_songs(
        self,
        genre: Optional[str] = None,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        energy: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search songs with filters."""
        conditions = []
        params = []
        param_idx = 1
        
        if genre:
            conditions.append(f"genre = ${param_idx}")
            params.append(genre)
            param_idx += 1
        
        if min_tempo is not None:
            conditions.append(f"tempo_bpm >= ${param_idx}")
            params.append(min_tempo)
            param_idx += 1
        
        if max_tempo is not None:
            conditions.append(f"tempo_bpm <= ${param_idx}")
            params.append(max_tempo)
            param_idx += 1
        
        if energy:
            conditions.append(f"energy = ${param_idx}")
            params.append(energy)
            param_idx += 1
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM songs WHERE {where_clause} ORDER BY title"
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [dict(row) for row in rows]
    
    # Audio analysis operations
    async def insert_audio_analysis(self, analysis: Dict[str, Any]) -> int:
        """Insert or update audio analysis."""
        query = """
            INSERT INTO audio_analysis (
                song_id, audio_url, bpm, key, energy, danceability,
                valence, acousticness, instrumentalness, liveness, speechiness
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (audio_url) DO UPDATE SET
                song_id = EXCLUDED.song_id,
                bpm = EXCLUDED.bpm,
                key = EXCLUDED.key,
                energy = EXCLUDED.energy,
                danceability = EXCLUDED.danceability,
                valence = EXCLUDED.valence,
                acousticness = EXCLUDED.acousticness,
                instrumentalness = EXCLUDED.instrumentalness,
                liveness = EXCLUDED.liveness,
                speechiness = EXCLUDED.speechiness,
                analyzed_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            analysis_id = await conn.fetchval(
                query,
                analysis.get('song_id'),
                analysis['audio_url'],
                analysis.get('bpm'),
                analysis.get('key'),
                analysis.get('energy'),
                analysis.get('danceability'),
                analysis.get('valence'),
                analysis.get('acousticness'),
                analysis.get('instrumentalness'),
                analysis.get('liveness'),
                analysis.get('speechiness')
            )
        
        logger.info(f"Inserted/updated audio analysis: {analysis_id}")
        return analysis_id
    
    async def get_audio_analysis(self, song_id: str) -> Optional[Dict[str, Any]]:
        """Get audio analysis for a song."""
        query = "SELECT * FROM audio_analysis WHERE song_id = $1"
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, song_id)
        
        return dict(row) if row else None
    
    # Vector operations for RAG
    async def insert_embedding(
        self,
        song_id: str,
        content_type: str,
        content: str,
        embedding: List[float]
    ) -> int:
        """Insert a song embedding."""
        query = """
            INSERT INTO song_embeddings (song_id, content_type, content, embedding)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            embedding_id = await conn.fetchval(
                query,
                song_id,
                content_type,
                content,
                embedding
            )
        
        return embedding_id
    
    async def search_similar_songs(
        self,
        query_embedding: List[float],
        limit: int = 5,
        content_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar songs using vector similarity."""
        type_filter = "AND content_type = $3" if content_type else ""
        query = f"""
            SELECT 
                se.song_id,
                se.content_type,
                se.content,
                s.title,
                s.genre,
                1 - (se.embedding <=> $1) as similarity
            FROM song_embeddings se
            JOIN songs s ON se.song_id = s.id
            WHERE 1=1 {type_filter}
            ORDER BY se.embedding <=> $1
            LIMIT $2
        """
        
        params = [query_embedding, limit]
        if content_type:
            params.append(content_type)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        return [dict(row) for row in rows]
    
    async def insert_document(
        self,
        source: str,
        content: str,
        metadata: Dict[str, Any],
        embedding: List[float]
    ) -> int:
        """Insert a document for RAG."""
        query = """
            INSERT INTO documents (source, content, metadata, embedding)
            VALUES ($1, $2, $3, $4)
            RETURNING id
        """
        
        async with self.pool.acquire() as conn:
            doc_id = await conn.fetchval(
                query,
                source,
                content,
                json.dumps(metadata),
                embedding
            )
        
        return doc_id
    
    async def search_documents(
        self,
        query_embedding: List[float],
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search documents using vector similarity."""
        query = """
            SELECT 
                id,
                source,
                content,
                metadata,
                1 - (embedding <=> $1) as similarity
            FROM documents
            ORDER BY embedding <=> $1
            LIMIT $2
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, query_embedding, limit)
        
        return [dict(row) for row in rows]
