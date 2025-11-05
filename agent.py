"""
Big Flavor Band AI Agent
An intelligent agent for managing song libraries, recommendations, and audio engineering.
"""

import asyncio
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from recommendation_engine import SongRecommendationEngine
from album_curator import AlbumCurator
from audio_analyzer import AudioAnalyzer
from mcp_server import BigFlavorMCPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("big-flavor-agent")


class BigFlavorAgent:
    """
    AI Agent for the Big Flavor band.
    Handles song recommendations, album curation, and audio engineering assistance.
    """
    
    def __init__(self, use_real_songs: bool = True, mcp_server_url: Optional[str] = None):
        """
        Initialize the Big Flavor Agent.
        
        Args:
            use_real_songs: If True, load real songs from MCP server. If False, use mock data.
            mcp_server_url: Optional MCP server URL (currently not used, direct integration)
        """
        self.use_real_songs = use_real_songs
        self.mcp_server_url = mcp_server_url
        self.mcp_server = BigFlavorMCPServer() if use_real_songs else None
        self.recommendation_engine = SongRecommendationEngine()
        self.album_curator = AlbumCurator()
        self.audio_analyzer = AudioAnalyzer()
        self.song_library = []
        logger.info(f"Big Flavor Agent initialized (use_real_songs={use_real_songs})")
    
    async def initialize(self):
        """Initialize the agent and load song library."""
        logger.info("Loading song library...")
        await self.load_song_library()
        logger.info(f"Loaded {len(self.song_library)} songs")
    
    async def load_song_library(self):
        """Load the song library from the MCP server or mock data."""
        if self.use_real_songs and self.mcp_server:
            logger.info("Fetching real songs from MCP server...")
            result = await self.mcp_server.get_song_library()
            if result['status'] == 'success':
                self.song_library = result['songs']
                logger.info(f"Successfully loaded {len(self.song_library)} real songs from RSS feed")
            else:
                logger.warning(f"Failed to load real songs: {result.get('message', 'Unknown error')}")
                logger.info("Falling back to mock data")
                self.song_library = self._get_mock_songs()
        else:
            logger.info("Using mock song data")
            self.song_library = self._get_mock_songs()
    
    async def refresh_song_library(self):
        """Refresh the song library from the MCP server."""
        logger.info("Refreshing song library...")
        await self.load_song_library()
        return {
            "status": "success",
            "total_songs": len(self.song_library),
            "message": "Song library refreshed"
        }
    
    async def search_songs(self, query: str) -> Dict[str, Any]:
        """
        Search for songs in the library.
        
        Args:
            query: Search query (searches title, genre, mood, tags)
        
        Returns:
            Dictionary with search results
        """
        if self.use_real_songs and self.mcp_server:
            return await self.mcp_server.search_songs(query)
        else:
            # Fallback search for mock data
            query_lower = query.lower()
            results = [
                song for song in self.song_library
                if query_lower in song.get("title", "").lower()
                or query_lower in song.get("genre", "").lower()
                or query_lower in song.get("mood", "").lower()
            ]
            return {
                "query": query,
                "results_count": len(results),
                "songs": results
            }
    
    async def get_song_by_id(self, song_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a song by its ID.
        
        Args:
            song_id: The song ID to retrieve
        
        Returns:
            Song dictionary or None if not found
        """
        if self.use_real_songs and self.mcp_server:
            result = await self.mcp_server.get_song_details(song_id)
            if result['status'] == 'found':
                return result['song']
            return None
        else:
            return next((s for s in self.song_library if s["id"] == song_id), None)
    
    async def filter_by_genre(self, genres: List[str]) -> Dict[str, Any]:
        """
        Filter songs by genre(s).
        
        Args:
            genres: List of genres to filter by
        
        Returns:
            Dictionary with filtered songs
        """
        if self.use_real_songs and self.mcp_server:
            return await self.mcp_server.filter_songs_by_genre(genres)
        else:
            genres_lower = [g.lower() for g in genres]
            results = [
                song for song in self.song_library
                if song.get("genre", "").lower() in genres_lower
            ]
            return {
                "genres": genres,
                "results_count": len(results),
                "songs": results
            }
    
    async def suggest_next_song(
        self, 
        current_song_id: Optional[str] = None,
        mood: Optional[str] = None,
        energy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Suggest what song to play next based on current song or preferences.
        
        Args:
            current_song_id: ID of the currently playing song
            mood: Desired mood (upbeat, melancholic, relaxed, energetic, fun)
            energy: Desired energy level (low, medium, high)
        
        Returns:
            Dictionary with suggested song and reasoning
        """
        logger.info(f"Generating next song suggestion (current: {current_song_id}, mood: {mood}, energy: {energy})")
        
        current_song = None
        if current_song_id:
            current_song = next((s for s in self.song_library if s["id"] == current_song_id), None)
        
        suggestion = await self.recommendation_engine.recommend_next_song(
            self.song_library,
            current_song=current_song,
            preferred_mood=mood,
            preferred_energy=energy
        )
        
        return suggestion
    
    async def suggest_similar_songs(self, song_id: str, limit: int = 5) -> Dict[str, Any]:
        """
        Find songs similar to a given song.
        
        Args:
            song_id: ID of the reference song
            limit: Maximum number of suggestions
        
        Returns:
            Dictionary with similar songs and similarity scores
        """
        logger.info(f"Finding similar songs to {song_id}")
        
        reference_song = next((s for s in self.song_library if s["id"] == song_id), None)
        if not reference_song:
            return {"error": f"Song {song_id} not found"}
        
        similar_songs = await self.recommendation_engine.find_similar_songs(
            reference_song,
            self.song_library,
            limit=limit
        )
        
        return similar_songs
    
    async def create_album_suggestion(
        self,
        theme: Optional[str] = None,
        song_ids: Optional[List[str]] = None,
        target_duration_minutes: int = 45
    ) -> Dict[str, Any]:
        """
        Create an album suggestion from the song library.
        
        Args:
            theme: Album theme (e.g., "upbeat rock", "mellow acoustic")
            song_ids: Optional list of song IDs to include
            target_duration_minutes: Target album duration in minutes
        
        Returns:
            Dictionary with album suggestion including track order and reasoning
        """
        logger.info(f"Creating album suggestion (theme: {theme}, duration: {target_duration_minutes}min)")
        
        selected_songs = self.song_library
        if song_ids:
            selected_songs = [s for s in self.song_library if s["id"] in song_ids]
        
        album = await self.album_curator.create_album(
            selected_songs,
            theme=theme,
            target_duration_minutes=target_duration_minutes
        )
        
        return album
    
    async def analyze_album_flow(self, song_ids: List[str]) -> Dict[str, Any]:
        """
        Analyze how well songs flow together in an album.
        
        Args:
            song_ids: Ordered list of song IDs
        
        Returns:
            Analysis of album flow with suggestions for improvement
        """
        logger.info(f"Analyzing album flow for {len(song_ids)} songs")
        
        songs = [s for s in self.song_library if s["id"] in song_ids]
        # Maintain the order specified by song_ids
        songs = sorted(songs, key=lambda s: song_ids.index(s["id"]))
        
        analysis = await self.album_curator.analyze_flow(songs)
        
        return analysis
    
    async def get_audio_engineering_suggestions(self, song_id: str) -> Dict[str, Any]:
        """
        Get audio engineering suggestions for improving song quality.
        
        Args:
            song_id: ID of the song to analyze
        
        Returns:
            Dictionary with engineering suggestions
        """
        logger.info(f"Generating audio engineering suggestions for {song_id}")
        
        song = next((s for s in self.song_library if s["id"] == song_id), None)
        if not song:
            return {"error": f"Song {song_id} not found"}
        
        suggestions = await self.audio_analyzer.analyze_and_suggest(song)
        
        return suggestions
    
    async def compare_song_quality(self, song_ids: List[str]) -> Dict[str, Any]:
        """
        Compare audio quality across multiple songs.
        
        Args:
            song_ids: List of song IDs to compare
        
        Returns:
            Comparison report with quality rankings
        """
        logger.info(f"Comparing quality of {len(song_ids)} songs")
        
        songs = [s for s in self.song_library if s["id"] in song_ids]
        comparison = await self.audio_analyzer.compare_quality(songs)
        
        return comparison
    
    async def suggest_setlist(
        self,
        duration_minutes: int = 60,
        energy_flow: str = "varied"  # varied, building, consistent
    ) -> Dict[str, Any]:
        """
        Suggest a setlist for a live performance.
        
        Args:
            duration_minutes: Target setlist duration
            energy_flow: How energy should flow (varied, building, consistent)
        
        Returns:
            Suggested setlist with performance notes
        """
        logger.info(f"Creating setlist ({duration_minutes}min, {energy_flow} energy)")
        
        setlist = await self.album_curator.create_setlist(
            self.song_library,
            target_duration_minutes=duration_minutes,
            energy_flow=energy_flow
        )
        
        return setlist
    
    def _get_mock_songs(self) -> List[Dict[str, Any]]:
        """Return mock song data matching the MCP server."""
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


async def main():
    """Main entry point for running the agent."""
    import sys
    
    # Check command line arguments for mode
    use_real_songs = True
    if len(sys.argv) > 1 and sys.argv[1] == "--mock":
        use_real_songs = False
    
    print("\n🎸 Big Flavor Band AI Agent 🎸")
    print("=" * 50)
    print(f"Mode: {'REAL SONGS from bigflavorband.com' if use_real_songs else 'MOCK DATA'}")
    print("=" * 50)
    
    agent = BigFlavorAgent(use_real_songs=use_real_songs)
    await agent.initialize()
    
    print(f"\n✅ Loaded {len(agent.song_library)} songs")
    
    if use_real_songs and len(agent.song_library) > 5:
        # Demo with real songs
        print("\n" + "=" * 50)
        print("REAL SONGS DEMO")
        print("=" * 50)
        
        # Show some real songs
        print("\n1. Sample of available songs:")
        for song in agent.song_library[:5]:
            print(f"   • {song['title']} - {song['album_session']} ({song['genre']})")
        
        # Search functionality
        print("\n2. Searching for 'tired' songs...")
        search_results = await agent.search_songs("tired")
        print(f"   Found {search_results['results_count']} songs")
        for song in search_results['songs'][:3]:
            print(f"   • {song['title']} ({song['full_title']})")
        
        # Filter by genre
        print("\n3. Finding Rock songs...")
        rock_songs = await agent.filter_by_genre(["Rock"])
        print(f"   Found {rock_songs['results_count']} Rock songs")
        for song in rock_songs['songs'][:3]:
            print(f"   • {song['title']}")
        
        # Suggest next song
        print("\n4. Suggesting next song after first song...")
        first_song_id = agent.song_library[0]['id']
        suggestion = await agent.suggest_next_song(current_song_id=first_song_id)
        print(f"   Suggested: {suggestion['suggested_song']['title']}")
        print(f"   Reason: {suggestion['reasoning']}")
        
        # Create album
        print("\n5. Creating a Rock album...")
        album = await agent.create_album_suggestion(theme="rock", target_duration_minutes=30)
        print(f"   Album: {album['album_name']}")
        print(f"   Tracks: {len(album['tracks'])}")
        for i, track in enumerate(album['tracks'][:5], 1):
            print(f"   {i}. {track['title']}")
    else:
        # Demo with mock data
        print("\n" + "=" * 50)
        print("MOCK DATA DEMO")
        print("=" * 50)
        
        # Demo: Suggest next song
        print("\n1. Suggesting next song after 'Summer Groove'...")
        suggestion = await agent.suggest_next_song(current_song_id="song_001")
        print(json.dumps(suggestion, indent=2))
        
        # Demo: Create album
        print("\n2. Creating an upbeat rock album...")
        album = await agent.create_album_suggestion(theme="upbeat rock", target_duration_minutes=30)
        print(json.dumps(album, indent=2))
        
        # Demo: Audio engineering suggestions
        print("\n3. Audio engineering suggestions for 'Midnight Blues'...")
        engineering = await agent.get_audio_engineering_suggestions("song_002")
        print(json.dumps(engineering, indent=2))
        
        # Demo: Create setlist
        print("\n4. Creating a 45-minute setlist...")
        setlist = await agent.suggest_setlist(duration_minutes=45, energy_flow="building")
        print(json.dumps(setlist, indent=2))
    
    print("\n" + "=" * 50)
    print("Demo complete!")
    print("\nTip: Run with --mock flag to use mock data instead of real songs")
    print("     python agent.py --mock")


if __name__ == "__main__":
    asyncio.run(main())
