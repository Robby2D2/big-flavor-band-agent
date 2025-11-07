"""
Big Flavor Band MCP Server
A Model Context Protocol server for audio production and analysis operations.
This server handles WRITE/PRODUCTION operations only.
READ/SEARCH operations are handled by the RAG system.
"""

import asyncio
import json
import logging
from typing import Any, Optional, List
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from audio_analysis_cache import AudioAnalysisCache
from database import DatabaseManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-mcp")


class BigFlavorMCPServer:
    """MCP Server for Big Flavor audio production and analysis operations."""
    
    def __init__(self, enable_audio_analysis: bool = True):
        self.app = Server("big-flavor-band-server")
        self.enable_audio_analysis = enable_audio_analysis
        self.audio_cache = AudioAnalysisCache() if enable_audio_analysis else None
        self.db_manager = None
        self.setup_handlers()
    
    async def initialize(self):
        """Initialize database connection."""
        try:
            self.db_manager = DatabaseManager()
            await self.db_manager.connect()
            logger.info("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def setup_handlers(self):
        """Set up MCP request handlers for production/write operations."""
        
        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """List available audio production tools."""
            return [
                Tool(
                    name="analyze_audio",
                    description="Extract tempo, key, beats, and other audio features from an audio file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file (MP3, WAV, etc.)"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="match_tempo",
                    description="Time-stretch audio to a specific BPM without changing pitch",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to time-stretch"
                            },
                            "target_bpm": {
                                "type": "number",
                                "description": "Target tempo in BPM"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for the processed file"
                            }
                        },
                        "required": ["file_path", "target_bpm", "output_path"]
                    }
                ),
                Tool(
                    name="create_transition",
                    description="Create a beat-matched DJ transition between two songs",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "song1_path": {
                                "type": "string",
                                "description": "Path to the first song"
                            },
                            "song2_path": {
                                "type": "string",
                                "description": "Path to the second song"
                            },
                            "transition_duration": {
                                "type": "number",
                                "description": "Duration of transition in seconds (default: 8)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for the transition"
                            }
                        },
                        "required": ["song1_path", "song2_path", "output_path"]
                    }
                ),
                Tool(
                    name="apply_mastering",
                    description="Apply professional mastering to make audio louder and more polished",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to master"
                            },
                            "target_loudness": {
                                "type": "number",
                                "description": "Target LUFS loudness (default: -14.0)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for the mastered file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="get_audio_cache_stats",
                    description="Get statistics about the audio analysis cache",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
            ]
        
        @self.app.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            """Handle tool execution requests."""
            try:
                if name == "analyze_audio":
                    result = await self.analyze_audio(arguments["file_path"])
                elif name == "get_song_details":
                    result = await self.get_song_details(arguments["song_id"])
                elif name == "filter_songs_by_genre":
                    result = await self.filter_songs_by_genre(arguments["genres"])
                elif name == "filter_songs_by_tempo":
                    result = await self.filter_songs_by_tempo(
                        arguments["min_tempo"], 
                        arguments["max_tempo"]
                    )
                elif name == "analyze_song_metadata":
                    result = await self.analyze_song_metadata(arguments["song_id"])
                elif name == "analyze_local_audio":
                    result = await self.analyze_local_audio(arguments["file_path"])
                elif name == "get_audio_cache_stats":
                    result = await self.get_audio_cache_stats()
                elif name == "semantic_search_by_audio":
                    await self.initialize_rag()
                    result = await self.semantic_search_by_audio(
                        arguments["audio_path"],
                        arguments.get("limit", 10),
                        arguments.get("similarity_threshold", 0.5)
                    )
                elif name == "get_similar_songs":
                    await self.initialize_rag()
                    result = await self.get_similar_songs(
                        arguments["song_id"],
                        arguments.get("limit", 10),
                        arguments.get("similarity_threshold", 0.5)
                    )
                elif name == "search_by_tempo_and_similarity":
                    await self.initialize_rag()
                    result = await self.search_by_tempo_and_similarity(
                        arguments["target_tempo"],
                        arguments.get("reference_audio_path"),
                        arguments.get("tempo_tolerance", 10.0),
                        arguments.get("limit", 10)
                    )
                elif name == "get_embedding_stats":
                    await self.initialize_rag()
                    result = await self.get_embedding_stats()
                elif name == "find_songs_without_embeddings":
                    await self.initialize_rag()
                    result = await self.find_songs_without_embeddings()
                elif name == "search_by_filters":
                    await self.initialize_rag()
                    result = await self.search_by_filters(
                        arguments.get("tempo_min"),
                        arguments.get("tempo_max"),
                        arguments.get("genre"),
                        arguments.get("title_keywords"),
                        arguments.get("limit", 10)
                    )
                else:
                    result = {"error": f"Unknown tool: {name}"}
                
                return [TextContent(
                    type="text",
                    text=json.dumps(result, indent=2)
                )]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(
                    type="text",
                    text=json.dumps({"error": str(e)})
                )]
    
    async def get_song_library(self) -> dict:
        """Fetch the complete song library from database."""
        try:
            await self.initialize_rag()
            
            if not self.db_manager:
                return {
                    "status": "error",
                    "error": "Database not available"
                }
            
            logger.info("Fetching song library from database")
            
            async with self.db_manager.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, 
                        title, 
                        genre, 
                        audio_url,
                        scraped_at
                    FROM songs 
                    ORDER BY title
                """)
                
                songs = [dict(row) for row in rows]
                self.songs_cache = songs
                self.last_fetch_time = datetime.now()
                
                logger.info(f"Successfully fetched {len(songs)} songs from database")
                
                return {
                    "status": "success",
                    "source": "database",
                    "total_songs": len(songs),
                    "last_updated": self.last_fetch_time.isoformat(),
                    "songs": songs
                }
        except Exception as e:
            logger.error(f"Error fetching song library from database: {e}")
            # Return error
            if not self.songs_cache:
                self.songs_cache = self._get_mock_songs()
            return {
                "status": "error",
                "message": f"Failed to fetch RSS feed: {str(e)}",
                "total_songs": len(self.songs_cache),
                "songs": self.songs_cache
            }
    
    async def search_songs(self, query: str) -> dict:
        """Search songs by query string using database."""
        try:
            await self.initialize_rag()
            
            if not self.db_manager:
                return {
                    "status": "error",
                    "error": "Database not available"
                }
            
            logger.info(f"Searching songs for query: {query}")
            query_lower = query.lower()
            
            # Search in database
            async with self.db_manager.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT 
                        id, 
                        title, 
                        genre, 
                        audio_url
                    FROM songs 
                    WHERE 
                        LOWER(title) LIKE $1
                        OR LOWER(genre) LIKE $1
                    ORDER BY title
                    LIMIT 100
                """, f"%{query_lower}%")
                
                results = [dict(row) for row in rows]
            
            logger.info(f"Found {len(results)} songs matching query")
            
            return {
                "query": query,
                "results_count": len(results),
                "songs": results
            }
        except Exception as e:
            logger.error(f"Error searching songs: {e}")
            return {
                "status": "error",
                "error": str(e),
                "query": query,
                "results_count": 0,
                "songs": []
            }
    
    async def get_song_details(self, song_id: str) -> dict:
        """Get detailed information about a specific song."""
        if not self.songs_cache:
            await self.get_song_library()
        
        song = next((s for s in self.songs_cache if s.get("id") == song_id), None)
        
        if song:
            return {"status": "found", "song": song}
        return {"status": "not_found", "song_id": song_id}
    
    async def filter_songs_by_genre(self, genres: list[str]) -> dict:
        """Filter songs by genres."""
        if not self.songs_cache:
            await self.get_song_library()
        
        genres_lower = [g.lower() for g in genres]
        results = [
            song for song in self.songs_cache
            if song.get("genre", "").lower() in genres_lower
        ]
        
        return {
            "genres": genres,
            "results_count": len(results),
            "songs": results
        }
    
    async def filter_songs_by_tempo(self, min_tempo: float, max_tempo: float) -> dict:
        """Filter songs by tempo range."""
        if not self.songs_cache:
            await self.get_song_library()
        
        results = [
            song for song in self.songs_cache
            if min_tempo <= song.get("tempo_bpm", 0) <= max_tempo
        ]
        
        return {
            "tempo_range": {"min": min_tempo, "max": max_tempo},
            "results_count": len(results),
            "songs": results
        }
    
    async def analyze_song_metadata(self, song_id: str) -> dict:
        """Analyze song metadata."""
        song_details = await self.get_song_details(song_id)
        
        if song_details["status"] == "not_found":
            return song_details
        
        song = song_details["song"]
        
        # Provide analysis based on metadata
        analysis = {
            "song_id": song_id,
            "title": song.get("title"),
            "characteristics": {
                "tempo": song.get("tempo_bpm"),
                "tempo_category": self._categorize_tempo(song.get("tempo_bpm", 120)),
                "key": song.get("key"),
                "energy_level": song.get("energy", "medium"),
                "mood": song.get("mood"),
                "genre": song.get("genre"),
            },
            "recommendations": self._generate_song_recommendations(song)
        }
        
        return analysis
    
    def _categorize_tempo(self, bpm: float) -> str:
        """Categorize tempo into descriptive categories."""
        if bpm < 80:
            return "slow"
        elif bpm < 120:
            return "moderate"
        elif bpm < 160:
            return "upbeat"
        else:
            return "fast"
    
    def _generate_song_recommendations(self, song: dict) -> dict:
        """Generate recommendations for a song."""
        return {
            "pairing_suggestions": "Songs with similar tempo and key work well together",
            "album_fit": f"Works well in {song.get('mood')} or {song.get('genre')} themed albums",
            "sound_engineering": [
                "Consider EQ adjustments to enhance clarity",
                "Compression can help balance dynamics",
                "Reverb settings should match the song's mood"
            ]
        }
    
    async def analyze_local_audio(self, file_path: str) -> dict:
        """
        Analyze a local audio file to extract BPM, key, genre hints, and energy.
        
        Args:
            file_path: Path to the local audio file
            
        Returns:
            Analysis results
        """
        if not self.audio_cache:
            return {
                "error": "Audio analysis is disabled",
                "message": "Enable audio analysis when initializing the server"
            }
        
        try:
            # The audio_url parameter is empty since this is a local file
            analysis = self.audio_cache.analyze_audio_file(file_path, audio_url="")
            
            return {
                "file_path": file_path,
                "analysis": analysis,
                "status": "success"
            }
        except Exception as e:
            logger.error(f"Error analyzing local audio file: {e}")
            return {
                "error": str(e),
                "file_path": file_path,
                "status": "error"
            }
    
    async def get_audio_cache_stats(self) -> dict:
        """Get statistics about the audio analysis cache."""
        if not self.audio_cache:
            return {
                "error": "Audio analysis is disabled",
                "message": "Enable audio analysis when initializing the server"
            }
        
        return self.audio_cache.get_cache_stats()
    
    def _parse_rss_feed(self, rss_content: str) -> list[dict]:
        """Parse RSS feed XML and extract song information."""
        try:
            root = ET.fromstring(rss_content)
            songs = []
            
            # Find all item elements in the RSS feed
            for idx, item in enumerate(root.findall('.//item')):
                try:
                    title = item.find('title')
                    link = item.find('link')
                    enclosure = item.find('enclosure')
                    pub_date = item.find('pubDate')
                    guid = item.find('guid')
                    
                    # Extract title (format: "Song Title - variant/performer")
                    song_title = title.text if title is not None and title.text else f"Untitled {idx+1}"
                    
                    # Parse title to extract song name and variant/performers
                    song_name, variant = self._parse_song_title(song_title)
                    
                    # Extract album/session name from link or guid
                    url_text = ""
                    if link is not None and link.text:
                        url_text = link.text
                    elif guid is not None and guid.text:
                        url_text = guid.text
                    album_session = self._extract_album_session(url_text)
                    
                    # Create song object
                    pub_date_text = pub_date.text if pub_date is not None and pub_date.text else ""
                    song = {
                        "id": f"song_{idx+1:04d}",
                        "title": song_name,
                        "full_title": song_title,
                        "variant": variant,
                        "album_session": album_session,
                        "url": link.text if link is not None and link.text else "",
                        "audio_url": enclosure.get('url') if enclosure is not None else "",
                        "audio_type": enclosure.get('type') if enclosure is not None else "",
                        "pub_date": pub_date_text,
                        "recording_date": self._parse_date(pub_date_text),
                        "genre": self._infer_genre(song_title, album_session),
                        "mood": self._infer_mood(song_title),
                        "tags": self._generate_tags(song_title, album_session),
                    }
                    
                    # Enrich with audio analysis from cache if available
                    if self.audio_cache and song["audio_url"]:
                        cached_analysis = self.audio_cache.get_cached_analysis(song["audio_url"])
                        if cached_analysis:
                            song = self._enrich_song_with_analysis(song, cached_analysis)
                    
                    songs.append(song)
                except Exception as e:
                    logger.warning(f"Error parsing RSS item {idx}: {e}")
                    continue
            
            return songs
        except Exception as e:
            logger.error(f"Error parsing RSS feed: {e}")
            return []
    
    def _parse_song_title(self, title: str) -> tuple[str, str]:
        """Parse song title to extract name and variant/performers."""
        # Titles are in format "Song Name - variant/performers"
        if ' - ' in title:
            parts = title.split(' - ', 1)
            return parts[0].strip(), parts[1].strip()
        return title.strip(), ""
    
    def _extract_album_session(self, url: str) -> str:
        """Extract album/session name from URL."""
        # URL format: https://bigflavorband.com/audio/####/Session Name--Song.mp3
        match = re.search(r'/audio/\d+/([^/]+?)--', url)
        if match:
            # Decode URL-encoded characters and clean up
            session = match.group(1).replace('+', ' ').replace('%20', ' ')
            return session
        return "Unknown Session"
    
    def _parse_date(self, date_str: str) -> str:
        """Parse publication date to ISO format."""
        try:
            # RSS date format: "Tue, 10 Jun 2025 02:57:24 GMT"
            dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
            return dt.strftime("%Y-%m-%d")
        except:
            return ""
    
    def _infer_genre(self, title: str, album: str) -> str:
        """Infer genre from song title and album name."""
        title_lower = title.lower()
        album_lower = album.lower()
        
        # Check for genre keywords
        if any(word in title_lower or word in album_lower for word in ['jazz', 'swing']):
            return "Jazz"
        elif any(word in title_lower or word in album_lower for word in ['blues', 'blue']):
            return "Blues"
        elif any(word in title_lower or word in album_lower for word in ['rock', 'metal']):
            return "Rock"
        elif any(word in title_lower or word in album_lower for word in ['acoustic', 'folk']):
            return "Acoustic/Folk"
        else:
            return "Rock/Alternative"  # Default genre for Big Flavor
    
    def _infer_mood(self, title: str) -> str:
        """Infer mood from song title."""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['tired', 'sad', 'blue', 'dark', 'helpless']):
            return "melancholic"
        elif any(word in title_lower for word in ['happy', 'joy', 'fun', 'party', 'celebrate']):
            return "upbeat"
        elif any(word in title_lower for word in ['love', 'heart', 'kiss']):
            return "romantic"
        elif any(word in title_lower for word in ['rock', 'roll', 'metal', 'fire']):
            return "energetic"
        else:
            return "reflective"
    
    def _generate_tags(self, title: str, album: str) -> list[str]:
        """Generate tags from song title and album."""
        tags = []
        
        # Add album as a tag
        if album and album != "Unknown Session":
            tags.append(album.replace(" ", "-").lower())
        
        # Add instrument/style tags from title
        title_lower = title.lower()
        if 'guitar' in title_lower or 'gtr' in title_lower:
            tags.append("guitar")
        if 'piano' in title_lower or 'keys' in title_lower:
            tags.append("piano")
        if 'drum' in title_lower:
            tags.append("drums")
        if 'bass' in title_lower:
            tags.append("bass")
        if 'vocal' in title_lower or 'sing' in title_lower:
            tags.append("vocals")
        if 'acoustic' in title_lower:
            tags.append("acoustic")
        if 'electric' in title_lower:
            tags.append("electric")
        if 'live' in title_lower:
            tags.append("live")
            
        return tags
    
    def _enrich_song_with_analysis(self, song: dict, analysis: dict) -> dict:
        """
        Enrich song metadata with audio analysis results.
        
        Args:
            song: Original song dictionary
            analysis: Audio analysis results
            
        Returns:
            Enriched song dictionary
        """
        # Add BPM if not already present or if analysis provides it
        if analysis.get('bpm') is not None:
            song['tempo_bpm'] = analysis['bpm']
        
        # Add key if available
        if analysis.get('key'):
            song['key'] = analysis['key']
        
        # Update energy level from analysis
        if analysis.get('energy'):
            song['energy'] = analysis['energy']
        
        # Add duration if available
        if analysis.get('duration_seconds'):
            song['duration_seconds'] = analysis['duration_seconds']
        
        # Enhance genre with hints from audio analysis
        if analysis.get('genre_hints'):
            # Keep the inferred genre but add analysis hints to tags
            for hint in analysis['genre_hints']:
                hint_tag = hint.lower().replace(' ', '-')
                if hint_tag not in song.get('tags', []):
                    song.setdefault('tags', []).append(hint_tag)
            
            # If no genre was inferred, use the first hint
            if not song.get('genre') or song.get('genre') == 'Rock/Alternative':
                if analysis['genre_hints']:
                    song['genre'] = analysis['genre_hints'][0]
        
        # Add analysis metadata
        song['audio_analysis'] = {
            'analyzed': True,
            'timestamp': analysis.get('analysis_timestamp', ''),
            'source': 'cached'
        }
        
        return song
    
    def _get_mock_songs(self) -> list[dict]:
        """Return mock song data for testing."""
        return [
            {
                "id": "song_001",
                "title": "Summer Groove",
                "genre": "Rock",
                "tempo_bpm": 128,
                "key": "C Major",
                "duration_seconds": 245,
                "energy": "high",
                "mood": "upbeat",
                "tags": ["summer", "fun", "energetic"],
                "recording_date": "2024-06-15",
                "audio_quality": "good"
            },
            {
                "id": "song_002",
                "title": "Midnight Blues",
                "genre": "Blues",
                "tempo_bpm": 88,
                "key": "E Minor",
                "duration_seconds": 312,
                "energy": "low",
                "mood": "melancholic",
                "tags": ["blues", "slow", "emotional"],
                "recording_date": "2024-03-22",
                "audio_quality": "fair"
            },
            {
                "id": "song_003",
                "title": "Weekend Warrior",
                "genre": "Rock",
                "tempo_bpm": 145,
                "key": "A Major",
                "duration_seconds": 198,
                "energy": "high",
                "mood": "energetic",
                "tags": ["rock", "fast", "powerful"],
                "recording_date": "2024-08-10",
                "audio_quality": "excellent"
            },
            {
                "id": "song_004",
                "title": "Coffee Shop Serenade",
                "genre": "Acoustic",
                "tempo_bpm": 102,
                "key": "G Major",
                "duration_seconds": 278,
                "energy": "medium",
                "mood": "relaxed",
                "tags": ["acoustic", "mellow", "chill"],
                "recording_date": "2024-05-05",
                "audio_quality": "good"
            },
            {
                "id": "song_005",
                "title": "Dad Rock Anthem",
                "genre": "Rock",
                "tempo_bpm": 132,
                "key": "D Major",
                "duration_seconds": 256,
                "energy": "high",
                "mood": "fun",
                "tags": ["rock", "dad-rock", "fun"],
                "recording_date": "2024-09-18",
                "audio_quality": "good"
            }
        ]
    
    # ==================== RAG System Methods ====================
    
    async def semantic_search_by_audio(
        self, 
        audio_path: str,
        limit: int = 10,
        similarity_threshold: float = 0.5
    ) -> dict:
        """
        Find songs that sound similar to a reference audio file.
        
        Args:
            audio_path: Path to reference audio file
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            Dictionary with search results and metadata
        """
        if not self.enable_rag or self.rag_system is None:
            return {
                "error": "RAG system not enabled or not initialized",
                "results": []
            }
        
        try:
            logger.info(f"Semantic audio search for: {audio_path}")
            results = await self.rag_system.search_by_audio_similarity(
                audio_path,
                limit=limit,
                similarity_threshold=similarity_threshold
            )
            
            return {
                "query_audio": audio_path,
                "total_results": len(results),
                "similarity_threshold": similarity_threshold,
                "results": results
            }
        except Exception as e:
            logger.error(f"Error in semantic audio search: {e}")
            return {
                "error": str(e),
                "results": []
            }
    
    async def get_similar_songs(
        self,
        song_id: str,
        limit: int = 10,
        similarity_threshold: float = 0.5
    ) -> dict:
        """
        Find songs similar to a given song using embeddings.
        
        Args:
            song_id: ID of reference song
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
        
        Returns:
            Dictionary with similar songs
        """
        if not self.enable_rag or self.rag_system is None:
            return {
                "error": "RAG system not enabled or not initialized",
                "results": []
            }
        
        try:
            # Get the embedding for this song
            embedding_data = await self.rag_system.get_song_embedding(song_id)
            
            if not embedding_data:
                return {
                    "error": f"No embedding found for song {song_id}",
                    "results": []
                }
            
            # Parse the embedding vector
            import ast
            combined_embedding = ast.literal_eval(embedding_data['combined_embedding'])
            
            # Search using this embedding
            results = await self.rag_system.search_by_embedding(
                combined_embedding,
                limit=limit + 1,  # +1 because the song itself will be in results
                similarity_threshold=similarity_threshold
            )
            
            # Filter out the query song itself
            filtered_results = [r for r in results if r.get('song_id') != song_id][:limit]
            
            return {
                "reference_song_id": song_id,
                "total_results": len(filtered_results),
                "similarity_threshold": similarity_threshold,
                "results": filtered_results
            }
        except Exception as e:
            logger.error(f"Error finding similar songs: {e}")
            return {
                "error": str(e),
                "results": []
            }
    
    async def search_by_tempo_and_similarity(
        self,
        target_tempo: float,
        reference_audio_path: Optional[str] = None,
        tempo_tolerance: float = 10.0,
        limit: int = 10
    ) -> dict:
        """
        Find songs with similar tempo and optionally similar sound.
        
        Args:
            target_tempo: Target BPM
            reference_audio_path: Optional audio file for sonic similarity
            tempo_tolerance: BPM tolerance (±)
            limit: Maximum number of results
        
        Returns:
            Dictionary with matching songs
        """
        if not self.enable_rag or self.rag_system is None:
            return {
                "error": "RAG system not enabled or not initialized",
                "results": []
            }
        
        try:
            logger.info(f"Tempo search: {target_tempo} BPM (±{tempo_tolerance})")
            
            results = await self.rag_system.search_by_tempo_and_audio(
                target_tempo=target_tempo,
                reference_audio_path=reference_audio_path,
                tempo_tolerance=tempo_tolerance,
                limit=limit
            )
            
            return {
                "target_tempo": target_tempo,
                "tempo_tolerance": tempo_tolerance,
                "reference_audio": reference_audio_path,
                "total_results": len(results),
                "results": results
            }
        except Exception as e:
            logger.error(f"Error in tempo search: {e}")
            return {
                "error": str(e),
                "results": []
            }
    
    async def get_embedding_stats(self) -> dict:
        """
        Get statistics about indexed song embeddings.
        
        Returns:
            Dictionary with embedding statistics
        """
        if not self.enable_rag or self.rag_system is None:
            return {
                "error": "RAG system not enabled or not initialized"
            }
        
        try:
            stats = await self.rag_system.get_embedding_stats()
            return {
                "status": "success",
                "statistics": stats
            }
        except Exception as e:
            logger.error(f"Error getting embedding stats: {e}")
            return {
                "error": str(e)
            }
    
    async def find_songs_without_embeddings(self) -> dict:
        """
        Find songs that haven't been indexed yet.
        
        Returns:
            Dictionary with unindexed songs
        """
        if not self.enable_rag or self.rag_system is None:
            return {
                "error": "RAG system not enabled or not initialized",
                "songs": []
            }
        
        try:
            songs = await self.rag_system.find_songs_without_embeddings()
            return {
                "status": "success",
                "total_unindexed": len(songs),
                "songs": songs
            }
        except Exception as e:
            logger.error(f"Error finding unindexed songs: {e}")
            return {
                "error": str(e),
                "songs": []
            }
    
    async def search_by_filters(
        self, 
        tempo_min: Optional[int] = None,
        tempo_max: Optional[int] = None,
        genre: Optional[str] = None,
        title_keywords: Optional[List[str]] = None,
        limit: int = 10
    ) -> dict:
        """
        Generic search by multiple filters. Let the LLM decide the parameters.
        
        Args:
            tempo_min: Minimum tempo in BPM (e.g., 120 for energetic songs)
            tempo_max: Maximum tempo in BPM (e.g., 90 for calm/sleep songs)
            genre: Genre to filter by (case-insensitive partial match)
            title_keywords: Keywords to search in title or genre (OR condition)
            limit: Maximum number of results
        
        Returns:
            Dictionary with search results
        """
        if not self.db_manager:
            return {
                "error": "Database not available",
                "songs": [],
                "results": []
            }
        
        try:
            logger.info(f"Filter search: tempo_min={tempo_min}, tempo_max={tempo_max}, genre={genre}, keywords={title_keywords}")
            
            # Build database query
            conditions = []
            params = []
            param_counter = 1
            
            # Always join audio_embeddings if we need tempo filtering
            needs_audio_join = tempo_min is not None or tempo_max is not None
            
            if genre:
                conditions.append(f"LOWER(s.genre) LIKE ${param_counter}")
                params.append(f"%{genre.lower()}%")
                param_counter += 1
            
            if tempo_min is not None:
                conditions.append(f"(ae.librosa_features->>'tempo')::float >= ${param_counter}")
                params.append(tempo_min)
                param_counter += 1
            
            if tempo_max is not None:
                conditions.append(f"(ae.librosa_features->>'tempo')::float <= ${param_counter}")
                params.append(tempo_max)
                param_counter += 1
            
            # Add keyword search in title or genre (optional)
            # Keywords are only used if no other filters are specified
            use_keywords_as_filter = not (tempo_min is not None or tempo_max is not None or genre)
            
            if title_keywords and use_keywords_as_filter:
                keyword_conditions = " OR ".join([f"LOWER(s.title) LIKE ${param_counter + i} OR LOWER(s.genre) LIKE ${param_counter + i}" for i in range(len(title_keywords))])
                conditions.append(f"({keyword_conditions})")
                params.extend([f"%{kw}%" for kw in title_keywords])
                param_counter += len(title_keywords)
            
            # Build final query
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            if needs_audio_join:
                # INNER JOIN to ensure we only get songs with embeddings
                query_sql = f"""
                    SELECT DISTINCT
                        s.id,
                        s.title,
                        s.genre,
                        s.audio_url,
                        (ae.librosa_features->>'tempo')::float as tempo_bpm
                    FROM songs s
                    INNER JOIN audio_embeddings ae ON s.id = ae.song_id
                    WHERE {where_clause}
                    ORDER BY tempo_bpm ASC
                    LIMIT ${param_counter}
                """
            else:
                # No tempo filtering, just search songs
                query_sql = f"""
                    SELECT DISTINCT
                        s.id,
                        s.title,
                        s.genre,
                        s.audio_url,
                        NULL as tempo_bpm
                    FROM songs s
                    WHERE {where_clause}
                    ORDER BY s.title
                    LIMIT ${param_counter}
                """
            params.append(limit)
            
            logger.info(f"Filter search SQL: {query_sql}")
            logger.info(f"Filter search params: {params}")
            
            async with self.db_manager.pool.acquire() as conn:
                rows = await conn.fetch(query_sql, *params)
                results = [dict(row) for row in rows]
            
            logger.info(f"Filter search found {len(results)} results")
            
            return {
                "status": "success",
                "filters_applied": {
                    "genre": genre,
                    "tempo_min": tempo_min,
                    "tempo_max": tempo_max,
                    "title_keywords": title_keywords
                },
                "total_results": len(results),
                "songs": results,
                "results": results  # Keep for backward compatibility
            }
            
        except Exception as e:
            logger.error(f"Error in filter search: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "songs": [],
                "results": []
            }
    
    async def run(self):
        """Run the MCP server."""
        try:
            async with stdio_server() as (read_stream, write_stream):
                await self.app.run(
                    read_stream,
                    write_stream,
                    self.app.create_initialization_options()
                )
        finally:
            # Cleanup database connection
            if self.db_manager:
                await self.db_manager.close()
                logger.info("Database connection closed")


async def main():
    """Main entry point for the MCP server."""
    server = BigFlavorMCPServer(enable_rag=True)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
