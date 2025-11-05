"""
Big Flavor Band MCP Server
A Model Context Protocol server for managing the Big Flavor band's song library.
"""

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import urljoin

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-mcp")


class BigFlavorMCPServer:
    """MCP Server for Big Flavor band song library management."""
    
    def __init__(self, base_url: str = "https://bigflavorband.com"):
        self.base_url = base_url
        self.app = Server("big-flavor-band-server")
        self.songs_cache = []
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
        """Fetch the complete song library."""
        try:
            # This is a placeholder - you'll need to implement actual scraping/API logic
            # for bigflavorband.com
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.base_url)
                
                # For now, return mock data structure
                # You would parse the actual HTML or API response here
                self.songs_cache = self._get_mock_songs()
                
                return {
                    "status": "success",
                    "total_songs": len(self.songs_cache),
                    "songs": self.songs_cache
                }
        except Exception as e:
            logger.error(f"Error fetching song library: {e}")
            # Return mock data if website is unavailable
            self.songs_cache = self._get_mock_songs()
            return {
                "status": "using_mock_data",
                "message": "Using sample data - implement website scraping for real data",
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
