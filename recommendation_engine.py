"""
Song Recommendation Engine
Provides intelligent song recommendations based on various factors.
"""

import logging
from typing import Dict, List, Optional, Any
import math

logger = logging.getLogger("recommendation-engine")


class SongRecommendationEngine:
    """Engine for recommending songs based on similarity and preferences."""
    
    # Musical key compatibility (circle of fifths)
    KEY_COMPATIBILITY = {
        "C Major": ["G Major", "F Major", "A Minor", "E Minor"],
        "G Major": ["D Major", "C Major", "E Minor", "B Minor"],
        "D Major": ["A Major", "G Major", "B Minor", "F# Minor"],
        "A Major": ["E Major", "D Major", "F# Minor", "C# Minor"],
        "E Major": ["B Major", "A Major", "C# Minor", "G# Minor"],
        "F Major": ["C Major", "Bb Major", "D Minor", "A Minor"],
        "A Minor": ["E Minor", "D Minor", "C Major", "F Major"],
        "E Minor": ["B Minor", "A Minor", "G Major", "D Major"],
        "B Minor": ["F# Minor", "E Minor", "D Major", "A Major"],
        "D Minor": ["A Minor", "G Minor", "F Major", "C Major"],
    }
    
    def __init__(self):
        """Initialize the recommendation engine."""
        logger.info("Recommendation engine initialized")
    
    async def recommend_next_song(
        self,
        song_library: List[Dict[str, Any]],
        current_song: Optional[Dict[str, Any]] = None,
        preferred_mood: Optional[str] = None,
        preferred_energy: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recommend the next song to play.
        
        Args:
            song_library: Complete library of songs
            current_song: Currently playing song (if any)
            preferred_mood: Desired mood
            preferred_energy: Desired energy level
        
        Returns:
            Recommendation with reasoning
        """
        if not song_library:
            return {"error": "No songs available in library"}
        
        # Score each song
        scored_songs = []
        for song in song_library:
            # Skip the current song
            if current_song and song["id"] == current_song["id"]:
                continue
            
            score = 0
            reasons = []
            
            # Base score: 50 points
            score += 50
            
            # If we have a current song, consider musical compatibility
            if current_song:
                # Tempo compatibility (within 20 BPM gets bonus)
                tempo_diff = abs(song["tempo_bpm"] - current_song["tempo_bpm"])
                if tempo_diff <= 20:
                    score += 20
                    reasons.append("Similar tempo for smooth transition")
                elif tempo_diff <= 40:
                    score += 10
                    reasons.append("Compatible tempo")
                
                # Key compatibility
                if self._are_keys_compatible(song["key"], current_song["key"]):
                    score += 25
                    reasons.append("Musically compatible key")
                
                # Genre match
                if song["genre"] == current_song["genre"]:
                    score += 15
                    reasons.append(f"Same genre ({song['genre']})")
            
            # Mood preference
            if preferred_mood and song["mood"] == preferred_mood:
                score += 30
                reasons.append(f"Matches desired mood ({preferred_mood})")
            
            # Energy preference
            if preferred_energy and song["energy"] == preferred_energy:
                score += 30
                reasons.append(f"Matches desired energy ({preferred_energy})")
            
            # Slight preference for higher quality recordings
            quality_scores = {"excellent": 10, "good": 5, "fair": 0}
            quality_bonus = quality_scores.get(song.get("audio_quality", "fair"), 0)
            score += quality_bonus
            if quality_bonus > 0:
                reasons.append(f"Good audio quality ({song['audio_quality']})")
            
            scored_songs.append({
                "song": song,
                "score": score,
                "reasons": reasons
            })
        
        # Sort by score (highest first)
        scored_songs.sort(key=lambda x: x["score"], reverse=True)
        
        if not scored_songs:
            return {"error": "No suitable songs found"}
        
        best_match = scored_songs[0]
        
        return {
            "recommended_song": {
                "id": best_match["song"]["id"],
                "title": best_match["song"]["title"],
                "genre": best_match["song"]["genre"],
                "tempo_bpm": best_match["song"]["tempo_bpm"],
                "mood": best_match["song"]["mood"],
                "energy": best_match["song"]["energy"]
            },
            "confidence_score": best_match["score"],
            "reasons": best_match["reasons"],
            "alternatives": [
                {
                    "id": alt["song"]["id"],
                    "title": alt["song"]["title"],
                    "score": alt["score"]
                }
                for alt in scored_songs[1:4]  # Top 3 alternatives
            ]
        }
    
    async def find_similar_songs(
        self,
        reference_song: Dict[str, Any],
        song_library: List[Dict[str, Any]],
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Find songs similar to a reference song.
        
        Args:
            reference_song: The song to find similarities to
            song_library: Complete library of songs
            limit: Maximum number of similar songs to return
        
        Returns:
            List of similar songs with similarity scores
        """
        similar_songs = []
        
        for song in song_library:
            if song["id"] == reference_song["id"]:
                continue
            
            similarity_score = self._calculate_similarity(reference_song, song)
            
            similar_songs.append({
                "song": song,
                "similarity_score": similarity_score,
                "matching_attributes": self._get_matching_attributes(reference_song, song)
            })
        
        # Sort by similarity (highest first)
        similar_songs.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return {
            "reference_song": {
                "id": reference_song["id"],
                "title": reference_song["title"]
            },
            "similar_songs": [
                {
                    "id": s["song"]["id"],
                    "title": s["song"]["title"],
                    "genre": s["song"]["genre"],
                    "similarity_score": s["similarity_score"],
                    "matching_attributes": s["matching_attributes"]
                }
                for s in similar_songs[:limit]
            ]
        }
    
    def _calculate_similarity(
        self,
        song1: Dict[str, Any],
        song2: Dict[str, Any]
    ) -> float:
        """Calculate similarity score between two songs (0-100)."""
        score = 0
        
        # Genre match (30 points)
        if song1["genre"] == song2["genre"]:
            score += 30
        
        # Mood match (25 points)
        if song1["mood"] == song2["mood"]:
            score += 25
        
        # Energy match (20 points)
        if song1["energy"] == song2["energy"]:
            score += 20
        
        # Tempo similarity (15 points max)
        tempo_diff = abs(song1["tempo_bpm"] - song2["tempo_bpm"])
        tempo_score = max(0, 15 - (tempo_diff / 10))
        score += tempo_score
        
        # Key compatibility (10 points)
        if self._are_keys_compatible(song1["key"], song2["key"]):
            score += 10
        
        return round(score, 2)
    
    def _get_matching_attributes(
        self,
        song1: Dict[str, Any],
        song2: Dict[str, Any]
    ) -> List[str]:
        """Get list of matching attributes between two songs."""
        matches = []
        
        if song1["genre"] == song2["genre"]:
            matches.append("genre")
        
        if song1["mood"] == song2["mood"]:
            matches.append("mood")
        
        if song1["energy"] == song2["energy"]:
            matches.append("energy")
        
        if abs(song1["tempo_bpm"] - song2["tempo_bpm"]) <= 20:
            matches.append("tempo")
        
        if self._are_keys_compatible(song1["key"], song2["key"]):
            matches.append("key")
        
        # Check for tag overlap
        tags1 = set(song1.get("tags", []))
        tags2 = set(song2.get("tags", []))
        if tags1 & tags2:  # If there's any overlap
            matches.append("tags")
        
        return matches
    
    def _are_keys_compatible(self, key1: str, key2: str) -> bool:
        """Check if two musical keys are compatible."""
        if key1 == key2:
            return True
        
        compatible_keys = self.KEY_COMPATIBILITY.get(key1, [])
        return key2 in compatible_keys
