"""
RAG System for Song Library
Manages retrieval-augmented generation over songs using audio and text embeddings.
Combines audio features (librosa + CLAP) with metadata for semantic search.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import hashlib
from datetime import datetime, timedelta
import numpy as np
import sys

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import from database package
from database import DatabaseManager

# Import audio embedding extractor
from src.rag.audio_embedding_extractor import AudioEmbeddingExtractor

logger = logging.getLogger("rag-system")


class SongRAGSystem:
    """
    RAG system for semantic search over song library.
    Supports audio similarity search, text search, and hybrid queries.
    """
    
    def __init__(
        self, 
        db_manager: DatabaseManager,
        use_clap: bool = True,
        cache_ttl_hours: int = 24
    ):
        """
        Initialize RAG system.
        
        Args:
            db_manager: Database manager instance
            use_clap: Whether to use CLAP for audio embeddings
            cache_ttl_hours: How long to cache search results (hours)
        """
        self.db = db_manager
        self.embedding_extractor = AudioEmbeddingExtractor(use_clap=use_clap)
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        logger.info("RAG system initialized")
    
    async def index_audio_file(self, audio_path: str, song_id: int) -> bool:
        """
        Extract embeddings from audio file and store in database.
        
        Args:
            audio_path: Path to audio file
            song_id: ID of the song in database (integer)
        
        Returns:
            True if successful
        """
        try:
            # Extract features
            features = self.embedding_extractor.extract_all_features(audio_path)
            
            # Store in database
            query = """
                INSERT INTO audio_embeddings (
                    song_id, audio_path, combined_embedding, clap_embedding, librosa_features
                ) VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (audio_path) DO UPDATE SET
                    song_id = EXCLUDED.song_id,
                    combined_embedding = EXCLUDED.combined_embedding,
                    clap_embedding = EXCLUDED.clap_embedding,
                    librosa_features = EXCLUDED.librosa_features,
                    extracted_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            async with self.db.pool.acquire() as conn:
                embedding_id = await conn.fetchval(
                    query,
                    song_id,
                    audio_path,
                    str(features['combined_embedding']),  # Convert to string for pgvector
                    str(features['clap_embedding']) if features['clap_embedding'] is not None else None,
                    json.dumps(features['librosa_features'])
                )
            
            logger.info(f"Indexed audio for song {song_id}: embedding_id={embedding_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index audio file {audio_path}: {e}")
            return False
    
    async def index_audio_batch(
        self, 
        audio_files: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """
        Index multiple audio files in batch.
        
        Args:
            audio_files: List of (audio_path, song_id) tuples
        
        Returns:
            Statistics about indexing
        """
        total = len(audio_files)
        success_count = 0
        failed = []
        
        logger.info(f"Starting batch indexing of {total} audio files")
        
        for i, (audio_path, song_id) in enumerate(audio_files, 1):
            logger.info(f"Processing {i}/{total}: {Path(audio_path).name}")
            
            if await self.index_audio_file(audio_path, song_id):
                success_count += 1
            else:
                failed.append((audio_path, song_id))
        
        stats = {
            'total': total,
            'success': success_count,
            'failed': len(failed),
            'failed_files': failed
        }
        
        logger.info(f"Batch indexing complete: {success_count}/{total} successful")
        return stats
    
    async def index_text_content(
        self, 
        song_id: int, 
        content_type: str, 
        content: str,
        text_embedding: List[float]
    ) -> bool:
        """
        Store text embedding for song metadata.
        
        Args:
            song_id: Song ID (integer)
            content_type: Type of content ('title', 'genre', 'description', etc.)
            content: Text content
            text_embedding: Pre-computed text embedding vector
        
        Returns:
            True if successful
        """
        try:
            query = """
                INSERT INTO text_embeddings (
                    song_id, content_type, content, embedding
                ) VALUES ($1, $2, $3, $4)
                ON CONFLICT (song_id, content_type) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    created_at = CURRENT_TIMESTAMP
                RETURNING id
            """
            
            async with self.db.pool.acquire() as conn:
                embedding_id = await conn.fetchval(
                    query,
                    song_id,
                    content_type,
                    content,
                    str(text_embedding)  # Convert to string for pgvector
                )
            
            logger.debug(f"Indexed text for song {song_id} ({content_type})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to index text for song {song_id}: {e}")
            return False
    
    async def extract_and_index_lyrics(
        self,
        audio_path: str,
        song_id: int,
        separate_vocals: bool = False,
        min_confidence: float = 0.5,
        generate_embedding: bool = True,
        vad_filter: bool = False,
        vad_min_silence_ms: int = 2000,
        vad_threshold: float = 0.3,
        apply_voice_filter: bool = False,
        whisper_model_size: str = 'large-v3',
        lyrics_extractor=None
    ) -> Dict[str, Any]:
        """
        Extract lyrics from audio and index them for RAG search.
        
        Args:
            audio_path: Path to audio file
            song_id: Song ID (integer)
            separate_vocals: Whether to use Demucs for vocal separation (slow)
            min_confidence: Minimum transcription confidence threshold
            generate_embedding: Whether to generate text embedding (requires OpenAI API)
            vad_filter: Enable voice activity detection (filters silence)
            vad_min_silence_ms: Minimum silence duration in ms before filtering (default 2000 = 2 seconds)
            vad_threshold: VAD sensitivity 0.0-1.0 (lower = more sensitive, default 0.3)
            apply_voice_filter: Apply voice frequency bandpass filter (80-8000 Hz)
            whisper_model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3')
            lyrics_extractor: Optional pre-initialized LyricsExtractor instance (for reuse across multiple songs)
            
        Returns:
            Dictionary with extraction results and metadata
        """
        try:
            # Import lyrics extractor
            from src.rag.lyrics_extractor import LyricsExtractor
            
            # Initialize lyrics extractor if not provided (only load demucs if vocal separation requested)
            if lyrics_extractor is None:
                lyrics_extractor = LyricsExtractor(
                    whisper_model_size=whisper_model_size,
                    use_gpu=True,
                    min_confidence=min_confidence,
                    load_demucs=separate_vocals
                )
            
            # Check if extractor is available
            if not lyrics_extractor.is_available():
                logger.warning("Lyrics extractor not available (missing dependencies)")
                return {
                    'success': False,
                    'error': 'Lyrics extractor dependencies not installed',
                    'song_id': song_id
                }
            
            # Extract lyrics
            logger.info(f"Extracting lyrics for song {song_id}: {audio_path}")
            result = lyrics_extractor.extract_lyrics(
                audio_path,
                separate_vocals=separate_vocals,
                vad_filter=vad_filter,
                vad_min_silence_ms=vad_min_silence_ms,
                vad_threshold=vad_threshold,
                apply_voice_filter=apply_voice_filter
            )
            
            # Check if extraction was successful
            if 'error' in result and result['error']:
                logger.error(f"Lyrics extraction failed for {song_id}: {result['error']}")
                return {
                    'success': False,
                    'error': result['error'],
                    'song_id': song_id
                }
            
            lyrics = result.get('lyrics', '').strip()
            confidence = result.get('confidence', 0.0)
            
            if not lyrics:
                logger.warning(f"No lyrics extracted for song {song_id}")
                return {
                    'success': False,
                    'error': 'No lyrics found',
                    'song_id': song_id,
                    'confidence': confidence
                }
            
            # Log extracted lyrics for monitoring
            lyrics_preview = lyrics[:200] + '...' if len(lyrics) > 200 else lyrics
            logger.info(f"Extracted lyrics for {song_id} ({len(lyrics)} chars, {confidence:.1%} confidence): {lyrics_preview}")
            
            # Store lyrics with placeholder embedding
            # TODO: Add real text embedding generation using sentence transformers or OpenAI
            success = await self.index_text_content(
                song_id=song_id,
                content_type='lyrics',
                content=lyrics,
                text_embedding=[0.0] * 384  # Placeholder for 384-dim text embeddings
            )
            
            return {
                'success': success,
                'song_id': song_id,
                'lyrics': lyrics,
                'confidence': confidence,
                'segments': len(result.get('segments', [])),
                'embedding_generated': False
            }
            
        except Exception as e:
            logger.error(f"Failed to extract and index lyrics for {song_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'song_id': song_id
            }
    
    async def batch_extract_lyrics(
        self,
        audio_files: List[Tuple[str, str]],
        separate_vocals: bool = False,
        min_confidence: float = 0.5,
        vad_filter: bool = False,
        vad_min_silence_ms: int = 2000,
        vad_threshold: float = 0.3,
        apply_voice_filter: bool = False,
        whisper_model_size: str = 'large-v3'
    ) -> Dict[str, Any]:
        """
        Extract lyrics from multiple audio files in batch.
        
        Args:
            audio_files: List of (audio_path, song_id) tuples
            separate_vocals: Whether to use vocal separation (slow)
            min_confidence: Minimum transcription confidence
            vad_filter: Enable voice activity detection (filters silence)
            vad_min_silence_ms: Minimum silence duration in ms before filtering (default 2000 = 2 seconds)
            vad_threshold: VAD sensitivity 0.0-1.0 (lower = more sensitive, default 0.3)
            apply_voice_filter: Apply voice frequency bandpass filter (80-8000 Hz)
            whisper_model_size: Whisper model size ('tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3')
            
        Returns:
            Statistics about lyrics extraction
        """
        total = len(audio_files)
        success_count = 0
        failed = []
        low_confidence = []
        
        logger.info(f"Starting batch lyrics extraction for {total} audio files")
        
        for i, (audio_path, song_id) in enumerate(audio_files, 1):
            logger.info(f"Processing lyrics {i}/{total}: {Path(audio_path).name}")
            
            result = await self.extract_and_index_lyrics(
                audio_path,
                song_id,
                separate_vocals=separate_vocals,
                min_confidence=min_confidence,
                generate_embedding=False,  # Skip embedding for batch processing
                vad_filter=vad_filter,
                vad_min_silence_ms=vad_min_silence_ms,
                vad_threshold=vad_threshold,
                apply_voice_filter=apply_voice_filter,
                whisper_model_size=whisper_model_size
            )
            
            if result['success']:
                success_count += 1
                if result.get('confidence', 0) < 0.7:
                    low_confidence.append((song_id, result.get('confidence', 0)))
            else:
                failed.append((audio_path, song_id, result.get('error', 'Unknown')))
        
        stats = {
            'total': total,
            'success': success_count,
            'failed': len(failed),
            'low_confidence_count': len(low_confidence),
            'failed_files': failed,
            'low_confidence_songs': low_confidence
        }
        
        logger.info(f"Batch lyrics extraction complete: {success_count}/{total} successful")
        return stats
    
    async def search_by_audio_similarity(
        self,
        query_audio_path: str,
        limit: int = 10,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Find songs similar to a query audio file.
        
        Args:
            query_audio_path: Path to query audio file
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            List of similar songs with similarity scores
        """
        # Extract features from query audio
        features = self.embedding_extractor.extract_all_features(query_audio_path)
        query_embedding = features['combined_embedding']
        
        # Search database
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_similar_songs_by_audio($1, $2, $3)
                """,
                str(query_embedding),  # Convert to string for pgvector
                limit,
                similarity_threshold
            )
        
        results = [dict(row) for row in rows]
        logger.info(f"Audio similarity search found {len(results)} results")
        return results
    
    async def search_by_embedding(
        self,
        query_embedding: List[float],
        limit: int = 10,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Search using a pre-computed embedding vector.
        
        Args:
            query_embedding: Embedding vector (549 dims)
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            List of similar songs
        """
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_similar_songs_by_audio($1, $2, $3)
                """,
                str(query_embedding),  # Convert to string for pgvector
                limit,
                similarity_threshold
            )
        
        results = [dict(row) for row in rows]
        return results
    
    async def search_by_text(
        self,
        query_embedding: List[float],
        content_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search songs by text embedding.
        
        Args:
            query_embedding: Text embedding vector (1536 dims for OpenAI)
            content_types: Which content types to search
            limit: Maximum number of results
        
        Returns:
            List of matching songs
        """
        if content_types is None:
            content_types = ['title', 'genre', 'description', 'tags']
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_similar_songs_by_text($1, $2, $3)
                """,
                str(query_embedding),  # Convert to string for pgvector
                limit,
                content_types
            )
        
        results = [dict(row) for row in rows]
        return results
    
    async def search_hybrid(
        self,
        audio_embedding: Optional[List[float]] = None,
        text_embedding: Optional[List[float]] = None,
        audio_weight: float = 0.6,
        text_weight: float = 0.4,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining audio and text similarity.
        
        Args:
            audio_embedding: Audio embedding vector (549 dims)
            text_embedding: Text embedding vector (1536 dims)
            audio_weight: Weight for audio similarity (0-1)
            text_weight: Weight for text similarity (0-1)
            limit: Maximum number of results
        
        Returns:
            List of songs with combined scores
        """
        if audio_embedding is None and text_embedding is None:
            raise ValueError("Must provide at least one embedding")
        
        # Use zero vectors if one is missing
        if audio_embedding is None:
            audio_embedding = [0.0] * 549
            audio_weight = 0.0
            text_weight = 1.0
        
        if text_embedding is None:
            text_embedding = [0.0] * 1536
            text_weight = 0.0
            audio_weight = 1.0
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_songs_hybrid($1, $2, $3, $4, $5)
                """,
                str(audio_embedding),  # Convert to string for pgvector
                str(text_embedding),  # Convert to string for pgvector
                audio_weight,
                text_weight,
                limit
            )
        
        results = [dict(row) for row in rows]
        logger.info(f"Hybrid search found {len(results)} results")
        return results
    
    async def search_by_tempo_range(
        self,
        min_tempo: Optional[float] = None,
        max_tempo: Optional[float] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find songs within a specific tempo range (BPM).
        
        Args:
            min_tempo: Minimum tempo in BPM (optional)
            max_tempo: Maximum tempo in BPM (optional)
            limit: Maximum number of results
        
        Returns:
            List of matching songs
        """
        conditions = []
        params = []
        param_count = 0
        
        if min_tempo is not None:
            param_count += 1
            conditions.append(f"(ae.librosa_features->>'tempo')::float >= ${param_count}")
            params.append(min_tempo)
        
        if max_tempo is not None:
            param_count += 1
            conditions.append(f"(ae.librosa_features->>'tempo')::float <= ${param_count}")
            params.append(max_tempo)
        
        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        param_count += 1
        params.append(limit)
        
        query = f"""
            SELECT 
                s.id,
                s.title,
                s.genre,
                ae.audio_path,
                (ae.librosa_features->>'tempo')::float as tempo_bpm
            FROM songs s
            JOIN audio_embeddings ae ON s.id = ae.song_id
            WHERE {where_clause}
            ORDER BY tempo_bpm
            LIMIT ${param_count}
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        
        results = [dict(row) for row in rows]
        logger.info(f"Tempo range search found {len(results)} results")
        return results
    
    async def search_by_text_description(
        self,
        description: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find songs matching a text description like 'ambient sleep music' or 'energetic workout beats'.
        Uses simple keyword matching across title, genre, and tags.
        
        Args:
            description: Text description of desired music
            limit: Maximum number of results
        
        Returns:
            List of matching songs
        """
        # Extract keywords from description
        keywords = description.lower().split()
        
        # Build search query with keyword matching
        query = """
            SELECT DISTINCT
                s.id,
                s.title,
                s.genre,
                s.audio_url,
                s.mood,
                s.energy,
                ae.audio_path,
                (ae.librosa_features->>'tempo')::float as tempo_bpm,
                COUNT(*) OVER (PARTITION BY s.id) as match_count
            FROM songs s
            LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
            WHERE 
                s.title ILIKE ANY($1) OR
                s.genre ILIKE ANY($1) OR
                s.mood ILIKE ANY($1) OR
                s.energy ILIKE ANY($1)
            ORDER BY match_count DESC, s.title
            LIMIT $2
        """
        
        # Create LIKE patterns for each keyword
        patterns = [f"%{keyword}%" for keyword in keywords]
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query, patterns, limit)
        
        results = [dict(row) for row in rows]
        logger.info(f"Text description search found {len(results)} results for '{description}'")
        return results
    
    async def search_by_tempo_and_audio(
        self,
        target_tempo: float,
        reference_audio_path: Optional[str] = None,
        tempo_tolerance: float = 10.0,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Find songs with similar tempo and optionally similar audio characteristics.
        
        Args:
            target_tempo: Target BPM
            reference_audio_path: Optional audio file to match sonically
            tempo_tolerance: BPM tolerance (±)
            limit: Maximum number of results
        
        Returns:
            List of matching songs
        """
        query_embedding = None
        
        if reference_audio_path:
            features = self.embedding_extractor.extract_all_features(reference_audio_path)
            query_embedding = features['combined_embedding']
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM search_by_tempo_and_audio($1, $2, $3, $4)
                """,
                target_tempo,
                tempo_tolerance,
                str(query_embedding) if query_embedding is not None else None,  # Convert to string
                limit
            )
        
        results = [dict(row) for row in rows]
        return results
    
    async def find_song_by_title(
        self,
        title: str,
        limit: int = 10,
        fuzzy: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Find songs by title with optional fuzzy matching.
        
        Args:
            title: Song title to search for
            limit: Maximum number of results
            fuzzy: If True, use fuzzy matching (ILIKE); if False, exact match
        
        Returns:
            List of matching songs with their audio paths
        """
        if fuzzy:
            # Use ILIKE for case-insensitive fuzzy matching
            # Order by length to prefer closer matches
            query = """
                SELECT 
                    s.id,
                    s.title,
                    s.genre,
                    s.audio_url,
                    s.mood,
                    s.energy,
                    ae.audio_path,
                    (ae.librosa_features->>'tempo')::float as tempo_bpm,
                    LENGTH(s.title) as title_length
                FROM songs s
                LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
                WHERE s.title ILIKE $1
                ORDER BY title_length, s.title
                LIMIT $2
            """
            pattern = f"%{title}%"
            
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(query, pattern, limit)
        else:
            # Exact match
            query = """
                SELECT 
                    s.id,
                    s.title,
                    s.genre,
                    s.audio_url,
                    s.mood,
                    s.energy,
                    ae.audio_path,
                    (ae.librosa_features->>'tempo')::float as tempo_bpm
                FROM songs s
                LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
                WHERE s.title = $1
                LIMIT $2
            """
            
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(query, title, limit)
        
        results = [dict(row) for row in rows]
        logger.info(f"Title search for '{title}' found {len(results)} results")
        return results
    
    async def get_song_embedding(self, song_id: str) -> Optional[Dict[str, Any]]:
        """
        Get stored embedding for a song.
        
        Args:
            song_id: Song ID
        
        Returns:
            Embedding data or None
        """
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM audio_embeddings WHERE song_id = $1
                """,
                song_id
            )
        
        return dict(row) if row else None
    
    async def find_songs_without_embeddings(self) -> List[Dict[str, Any]]:
        """
        Find songs that don't have audio embeddings yet.
        
        Returns:
            List of songs needing indexing
        """
        query = """
            SELECT s.id, s.title, s.audio_url
            FROM songs s
            LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
            WHERE ae.id IS NULL AND s.audio_url IS NOT NULL
            ORDER BY s.title
        """
        
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch(query)
        
        return [dict(row) for row in rows]
    
    async def get_embedding_stats(self) -> Dict[str, Any]:
        """
        Get statistics about indexed embeddings.
        
        Returns:
            Statistics dictionary
        """
        async with self.db.pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT 
                    COUNT(DISTINCT ae.song_id) as songs_with_audio_embeddings,
                    COUNT(DISTINCT te.song_id) as songs_with_text_embeddings,
                    COUNT(DISTINCT s.id) as total_songs,
                    AVG((ae.librosa_features->>'tempo')::float) as avg_tempo
                FROM songs s
                LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
                LEFT JOIN text_embeddings te ON s.id = te.song_id
                """
            )
        
        return dict(stats)
    
    def _compute_query_hash(self, query_params: Dict[str, Any]) -> str:
        """Compute hash for caching search queries."""
        query_str = json.dumps(query_params, sort_keys=True)
        return hashlib.sha256(query_str.encode()).hexdigest()
    
    async def cleanup_cache(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of entries removed
        """
        async with self.db.pool.acquire() as conn:
            deleted = await conn.fetchval("SELECT cleanup_expired_cache()")
        
        logger.info(f"Cleaned up {deleted} expired cache entries")
        return deleted


async def main():
    """Test the RAG system."""
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize database
    db = DatabaseManager()
    await db.connect()
    
    # Initialize RAG system
    rag = SongRAGSystem(db, use_clap=True)
    
    # Get stats
    stats = await rag.get_embedding_stats()
    print("\n=== RAG System Stats ===")
    print(f"Total songs: {stats['total_songs']}")
    print(f"Songs with audio embeddings: {stats['songs_with_audio_embeddings']}")
    print(f"Songs with text embeddings: {stats['songs_with_text_embeddings']}")
    
    # Find songs without embeddings
    missing = await rag.find_songs_without_embeddings()
    print(f"\nSongs without embeddings: {len(missing)}")
    
    if len(sys.argv) > 1:
        # Test search
        query_audio = sys.argv[1]
        print(f"\nSearching for songs similar to: {query_audio}")
        
        results = await rag.search_by_audio_similarity(
            query_audio,
            limit=5,
            similarity_threshold=0.3
        )
        
        print("\n=== Top 5 Similar Songs ===")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']} - {result['genre']} ({result['similarity']:.3f})")
            print(f"   Tempo: {result['tempo_bpm']:.1f} BPM")
            print(f"   Path: {result['audio_path']}")
    
    await db.close()


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
