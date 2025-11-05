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
    
    def __init__(self, mcp_server_url: Optional[str] = None):
        """Initialize the Big Flavor Agent."""
        self.mcp_server_url = mcp_server_url
        self.recommendation_engine = SongRecommendationEngine()
        self.album_curator = AlbumCurator()
        self.audio_analyzer = AudioAnalyzer()
        self.song_library = []
        logger.info("Big Flavor Agent initialized")
    
    async def initialize(self):
        """Initialize the agent and load song library."""
        logger.info("Loading song library...")
        # In a full implementation, this would connect to the MCP server
        # For now, we'll use the mock data structure
        await self.load_song_library()
        logger.info(f"Loaded {len(self.song_library)} songs")
    
    async def load_song_library(self):
        """Load the song library from the MCP server."""
        # Placeholder for MCP server integration
        # In production, this would make a call to the MCP server
        self.song_library = self._get_mock_songs()
    
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
    agent = BigFlavorAgent()
    await agent.initialize()
    
    print("\n🎸 Big Flavor Band AI Agent 🎸")
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


if __name__ == "__main__":
    asyncio.run(main())
