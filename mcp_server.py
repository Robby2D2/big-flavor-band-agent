"""
Big Flavor Band MCP Server
A Model Context Protocol server for managing the Big Flavor band's song library.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import urljoin
from datetime import datetime
import xml.etree.ElementTree as ET
import re

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from audio_analysis_cache import AudioAnalysisCache

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-mcp")


class BigFlavorMCPServer:
    """MCP Server for Big Flavor band song library management."""
    
    def __init__(self, base_url: str = "https://bigflavorband.com", enable_audio_analysis: bool = True):
        self.base_url = base_url
        self.rss_url = f"{base_url}/rss"
        self.app = Server("big-flavor-band-server")
        self.songs_cache = []
        self.last_fetch_time = None
        self.enable_audio_analysis = enable_audio_analysis
        self.audio_cache = AudioAnalysisCache() if enable_audio_analysis else None
        self.setup_handlers()
    
    def setup_handlers(self):
        """Set up MCP request handlers."""
        
        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """List available tools for the Big Flavor band agent."""
            return [
                Tool(
                    name="get_song_library",
                    description="Fetch the complete song library from bigflavorband.com",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="search_songs",
                    description="Search for songs by title, artist, genre, or mood",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for song title, genre, or mood"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="get_song_details",
                    description="Get detailed information about a specific song",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "song_id": {
                                "type": "string",
                                "description": "Unique identifier for the song"
                            }
                        },
                        "required": ["song_id"]
                    }
                ),
                Tool(
                    name="filter_songs_by_genre",
                    description="Filter songs by specific genre(s)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "genres": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of genres to filter by"
                            }
                        },
                        "required": ["genres"]
                    }
                ),
                Tool(
                    name="filter_songs_by_tempo",
                    description="Filter songs by tempo range (BPM)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "min_tempo": {
                                "type": "number",
                                "description": "Minimum tempo in BPM"
                            },
                            "max_tempo": {
                                "type": "number",
                                "description": "Maximum tempo in BPM"
                            }
                        },
                        "required": ["min_tempo", "max_tempo"]
                    }
                ),
                Tool(
                    name="analyze_song_metadata",
                    description="Analyze metadata of a song including key, tempo, energy, mood",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "song_id": {
                                "type": "string",
                                "description": "Song identifier to analyze"
                            }
                        },
                        "required": ["song_id"]
                    }
                ),
                Tool(
                    name="analyze_local_audio",
                    description="Analyze a local audio file to extract BPM, key, genre hints, and energy",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the local audio file (MP3, WAV, etc.)"
                            }
                        },
                        "required": ["file_path"]
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
                if name == "get_song_library":
                    result = await self.get_song_library()
                elif name == "search_songs":
                    result = await self.search_songs(arguments["query"])
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
        """Fetch the complete song library from RSS feed."""
        try:
            logger.info(f"Fetching song library from {self.rss_url}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.rss_url)
                response.raise_for_status()
                
                # Parse RSS feed
                self.songs_cache = self._parse_rss_feed(response.text)
                self.last_fetch_time = datetime.now()
                
                logger.info(f"Successfully fetched {len(self.songs_cache)} songs from RSS feed")
                
                return {
                    "status": "success",
                    "source": "bigflavorband.com RSS feed",
                    "total_songs": len(self.songs_cache),
                    "last_updated": self.last_fetch_time.isoformat(),
                    "songs": self.songs_cache
                }
        except Exception as e:
            logger.error(f"Error fetching song library from RSS: {e}")
            # Return mock data if RSS is unavailable
            if not self.songs_cache:
                self.songs_cache = self._get_mock_songs()
            return {
                "status": "error",
                "message": f"Failed to fetch RSS feed: {str(e)}",
                "total_songs": len(self.songs_cache),
                "songs": self.songs_cache
            }
    
    async def search_songs(self, query: str) -> dict:
        """Search songs by query string."""
        if not self.songs_cache:
            await self.get_song_library()
        
        query_lower = query.lower()
        results = [
            song for song in self.songs_cache
            if query_lower in song.get("title", "").lower()
            or query_lower in song.get("genre", "").lower()
            or query_lower in song.get("mood", "").lower()
            or query_lower in " ".join(song.get("tags", [])).lower()
        ]
        
        return {
            "query": query,
            "results_count": len(results),
            "songs": results
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
    
    async def run(self):
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.app.run(
                read_stream,
                write_stream,
                self.app.create_initialization_options()
            )


async def main():
    """Main entry point for the MCP server."""
    server = BigFlavorMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
