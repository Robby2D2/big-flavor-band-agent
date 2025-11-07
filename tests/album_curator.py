"""
Album Curator
Creates album suggestions and analyzes song flow.
"""

import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger("album-curator")

# Default duration for songs without duration_seconds (3.5 minutes)
DEFAULT_SONG_DURATION = 210


def get_song_duration(song: Dict[str, Any]) -> int:
    """
    Get song duration in seconds, using default if not available.
    
    Args:
        song: Song dictionary
    
    Returns:
        Duration in seconds
    """
    return song.get("duration_seconds", DEFAULT_SONG_DURATION)


class AlbumCurator:
    """Curator for creating albums and setlists from song libraries."""
    
    def __init__(self):
        """Initialize the album curator."""
        logger.info("Album curator initialized")
    
    async def create_album(
        self,
        song_library: List[Dict[str, Any]],
        theme: Optional[str] = None,
        target_duration_minutes: int = 45
    ) -> Dict[str, Any]:
        """
        Create an album suggestion from available songs.
        
        Args:
            song_library: Available songs
            theme: Optional theme (e.g., "upbeat rock", "mellow acoustic")
            target_duration_minutes: Target album duration
        
        Returns:
            Album with track listing and metadata
        """
        if not song_library:
            return {"error": "No songs available"}
        
        # Filter songs by theme if provided
        filtered_songs = self._filter_by_theme(song_library, theme) if theme else song_library
        
        if not filtered_songs:
            return {"error": f"No songs match theme: {theme}"}
        
        # Select songs for the album
        selected_songs = self._select_songs_for_duration(
            filtered_songs,
            target_duration_minutes * 60  # Convert to seconds
        )
        
        # Order songs for optimal flow
        ordered_tracks = self._order_tracks(selected_songs)
        
        # Calculate total duration
        total_duration_seconds = sum(get_song_duration(song) for song in ordered_tracks)
        
        return {
            "album_name": self._generate_album_name(theme, ordered_tracks),
            "theme": theme or "mixed",
            "total_duration_minutes": round(total_duration_seconds / 60, 1),
            "track_count": len(ordered_tracks),
            "tracks": [
                {
                    "track_number": idx + 1,
                    "id": song["id"],
                    "title": song["title"],
                    "duration_seconds": get_song_duration(song),
                    "genre": song["genre"],
                    "tempo_bpm": song.get("tempo_bpm"),
                    "mood": song["mood"]
                }
                for idx, song in enumerate(ordered_tracks)
            ],
            "curation_notes": self._generate_curation_notes(ordered_tracks, theme)
        }
    
    async def analyze_flow(self, songs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze how well songs flow together.
        
        Args:
            songs: Ordered list of songs
        
        Returns:
            Flow analysis with suggestions
        """
        if len(songs) < 2:
            return {"error": "Need at least 2 songs to analyze flow"}
        
        transitions = []
        issues = []
        suggestions = []
        
        for i in range(len(songs) - 1):
            current = songs[i]
            next_song = songs[i + 1]
            
            transition_analysis = self._analyze_transition(current, next_song, i + 1)
            transitions.append(transition_analysis)
            
            if transition_analysis["quality"] == "poor":
                issues.append(transition_analysis["issue"])
                suggestions.append(transition_analysis["suggestion"])
        
        # Calculate overall flow score
        avg_score = sum(t["score"] for t in transitions) / len(transitions)
        
        flow_rating = "excellent" if avg_score >= 80 else "good" if avg_score >= 60 else "fair" if avg_score >= 40 else "poor"
        
        return {
            "overall_flow_score": round(avg_score, 2),
            "flow_rating": flow_rating,
            "transitions": transitions,
            "issues": issues,
            "improvement_suggestions": suggestions,
            "track_order": [
                {
                    "position": idx + 1,
                    "title": song["title"],
                    "id": song["id"]
                }
                for idx, song in enumerate(songs)
            ]
        }
    
    async def create_setlist(
        self,
        song_library: List[Dict[str, Any]],
        target_duration_minutes: int = 60,
        energy_flow: str = "varied"
    ) -> Dict[str, Any]:
        """
        Create a setlist for live performance.
        
        Args:
            song_library: Available songs
            target_duration_minutes: Target setlist duration
            energy_flow: Energy flow pattern (varied, building, consistent)
        
        Returns:
            Setlist with performance notes
        """
        if not song_library:
            return {"error": "No songs available"}
        
        # Select songs based on energy flow pattern
        selected_songs = self._select_songs_for_setlist(
            song_library,
            target_duration_minutes * 60,
            energy_flow
        )
        
        return {
            "setlist_name": f"Big Flavor {energy_flow.title()} Energy Set",
            "duration_minutes": round(sum(get_song_duration(s) for s in selected_songs) / 60, 1),
            "energy_flow": energy_flow,
            "songs": [
                {
                    "position": idx + 1,
                    "id": song["id"],
                    "title": song["title"],
                    "duration_minutes": round(get_song_duration(song) / 60, 1),
                    "energy": song.get("energy", "medium"),
                    "performance_notes": self._generate_performance_notes(song, idx + 1, len(selected_songs))
                }
                for idx, song in enumerate(selected_songs)
            ],
            "setlist_notes": self._generate_setlist_notes(selected_songs, energy_flow)
        }
    
    def _filter_by_theme(
        self,
        songs: List[Dict[str, Any]],
        theme: str
    ) -> List[Dict[str, Any]]:
        """Filter songs that match the given theme."""
        theme_lower = theme.lower()
        
        filtered = []
        for song in songs:
            # Check if theme words appear in genre, mood, or tags
            matches_theme = (
                theme_lower in song["genre"].lower() or
                theme_lower in song["mood"].lower() or
                any(theme_lower in tag.lower() for tag in song.get("tags", []))
            )
            
            # Also check individual words from theme
            theme_words = theme_lower.split()
            for word in theme_words:
                if (word in song["genre"].lower() or
                    word in song["mood"].lower() or
                    any(word in tag.lower() for tag in song.get("tags", []))):
                    matches_theme = True
                    break
            
            if matches_theme:
                filtered.append(song)
        
        return filtered
    
    def _select_songs_for_duration(
        self,
        songs: List[Dict[str, Any]],
        target_seconds: int
    ) -> List[Dict[str, Any]]:
        """Select songs to approximately match target duration."""
        selected = []
        current_duration = 0
        
        # Estimate duration for songs that don't have it (assume 3.5 minutes average)
        DEFAULT_DURATION = 210  # 3.5 minutes in seconds
        
        # Sort by quality and variety
        sorted_songs = sorted(
            songs,
            key=lambda s: (
                {"excellent": 3, "good": 2, "fair": 1}.get(s.get("audio_quality", "fair"), 0),
                -abs(current_duration + s.get("duration_seconds", DEFAULT_DURATION) - target_seconds)
            ),
            reverse=True
        )
        
        for song in sorted_songs:
            song_duration = song.get("duration_seconds", DEFAULT_DURATION)
            if current_duration + song_duration <= target_seconds * 1.1:  # 10% buffer
                selected.append(song)
                current_duration += song_duration
                
                if current_duration >= target_seconds * 0.9:  # At least 90% of target
                    break
        
        return selected
    
    def _order_tracks(self, songs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Order tracks for optimal album flow."""
        if len(songs) <= 2:
            return songs
        
        # Strategy: Start with medium energy, vary throughout, end strong
        ordered = []
        
        # Categorize by energy
        high_energy = [s for s in songs if s.get("energy") == "high"]
        medium_energy = [s for s in songs if s.get("energy") == "medium"]
        low_energy = [s for s in songs if s.get("energy") == "low"]
        
        # Start with a medium or medium-high energy song
        if medium_energy:
            ordered.append(medium_energy.pop(0))
        elif high_energy:
            ordered.append(high_energy.pop(0))
        
        # Alternate energy levels for variety
        remaining = high_energy + medium_energy + low_energy
        
        while remaining:
            # Try to vary from the last song
            last_energy = ordered[-1].get("energy", "medium") if ordered else "medium"
            
            # Pick a song with different energy if possible
            next_song = None
            for energy_level in ["low", "medium", "high"]:
                if energy_level != last_energy:
                    candidates = [s for s in remaining if s.get("energy") == energy_level]
                    if candidates:
                        next_song = candidates[0]
                        remaining.remove(next_song)
                        break
            
            if not next_song:
                next_song = remaining.pop(0)
            
            ordered.append(next_song)
        
        return ordered
    
    def _analyze_transition(
        self,
        current: Dict[str, Any],
        next_song: Dict[str, Any],
        transition_number: int
    ) -> Dict[str, Any]:
        """Analyze the transition between two songs."""
        score = 50  # Base score
        quality = "good"
        issue = None
        suggestion = None
        
        # Tempo analysis (skip if tempo data not available)
        current_tempo = current.get("tempo_bpm")
        next_tempo = next_song.get("tempo_bpm")
        
        if current_tempo and next_tempo:
            tempo_diff = abs(current_tempo - next_tempo)
            if tempo_diff <= 15:
                score += 25
            elif tempo_diff <= 30:
                score += 15
            elif tempo_diff > 50:
                score -= 20
                quality = "poor"
                issue = f"Large tempo jump ({current_tempo} → {next_tempo} BPM)"
                suggestion = f"Consider a transitional song or reorder tracks {transition_number} and {transition_number + 1}"
        
        # Energy flow
        energy_map = {"low": 1, "medium": 2, "high": 3}
        current_energy = current.get("energy", "medium")
        next_energy = next_song.get("energy", "medium")
        energy_diff = abs(energy_map[current_energy] - energy_map[next_energy])
        
        if energy_diff == 0:
            score += 15
        elif energy_diff == 1:
            score += 20  # Natural progression
        else:  # energy_diff == 2
            score -= 15
            if not issue:
                quality = "fair"
                issue = f"Abrupt energy change ({current_energy} → {next_energy})"
                suggestion = f"Add a medium-energy song between tracks {transition_number} and {transition_number + 1}"
        
        # Genre consistency
        if current["genre"] == next_song["genre"]:
            score += 10
        
        # Overall quality assessment
        if score >= 80:
            quality = "excellent"
        elif score >= 60:
            quality = "good"
        elif score >= 40:
            quality = "fair"
        else:
            quality = "poor"
        
        return {
            "from_song": current["title"],
            "to_song": next_song["title"],
            "transition_number": transition_number,
            "score": score,
            "quality": quality,
            "issue": issue,
            "suggestion": suggestion
        }
    
    def _select_songs_for_setlist(
        self,
        songs: List[Dict[str, Any]],
        target_seconds: int,
        energy_flow: str
    ) -> List[Dict[str, Any]]:
        """Select and order songs for a setlist based on energy flow."""
        high_energy = [s for s in songs if s.get("energy") == "high"]
        medium_energy = [s for s in songs if s.get("energy") == "medium"]
        low_energy = [s for s in songs if s.get("energy") == "low"]
        
        selected = []
        current_duration = 0
        
        if energy_flow == "building":
            # Start low/medium, build to high
            pool = low_energy + medium_energy + high_energy
        elif energy_flow == "consistent":
            # Maintain similar energy throughout
            pool = medium_energy + high_energy + low_energy
        else:  # varied
            # Mix energy levels
            pool = []
            while high_energy or medium_energy or low_energy:
                if medium_energy:
                    pool.append(medium_energy.pop(0))
                if high_energy:
                    pool.append(high_energy.pop(0))
                if low_energy:
                    pool.append(low_energy.pop(0))
        
        for song in pool:
            song_duration = get_song_duration(song)
            if current_duration + song_duration <= target_seconds * 1.1:
                selected.append(song)
                current_duration += song_duration
                
                if current_duration >= target_seconds * 0.9:
                    break
        
        return selected
    
    def _generate_album_name(
        self,
        theme: Optional[str],
        tracks: List[Dict[str, Any]]
    ) -> str:
        """Generate an album name based on theme and tracks."""
        if theme:
            return f"Big Flavor: {theme.title()}"
        
        # Generate based on dominant mood/genre
        genres = [t["genre"] for t in tracks]
        most_common_genre = max(set(genres), key=genres.count)
        
        return f"Big Flavor: {most_common_genre} Collection"
    
    def _generate_curation_notes(
        self,
        tracks: List[Dict[str, Any]],
        theme: Optional[str]
    ) -> List[str]:
        """Generate notes about the album curation."""
        notes = []
        
        if theme:
            notes.append(f"Album curated around '{theme}' theme")
        
        total_duration = sum(get_song_duration(t) for t in tracks)
        notes.append(f"Total runtime: {round(total_duration / 60, 1)} minutes across {len(tracks)} tracks")
        
        # Energy flow
        energy_flow = " → ".join([t.get("energy", "medium") for t in tracks])
        notes.append(f"Energy progression: {energy_flow}")
        
        # Genre distribution
        genres = [t["genre"] for t in tracks]
        unique_genres = set(genres)
        if len(unique_genres) == 1:
            notes.append(f"Consistent {list(unique_genres)[0]} sound throughout")
        else:
            notes.append(f"Blends {', '.join(unique_genres)} genres")
        
        return notes
    
    def _generate_performance_notes(
        self,
        song: Dict[str, Any],
        position: int,
        total_songs: int
    ) -> str:
        """Generate performance notes for a song in a setlist."""
        if position == 1:
            return "Strong opener - set the energy for the show"
        elif position == total_songs:
            return "Closer - leave them wanting more!"
        elif position == total_songs // 2:
            return "Mid-set anchor - good time for band banter"
        elif song.get("energy") == "high":
            return "High energy - get the crowd moving"
        elif song.get("energy") == "low":
            return "Breather - let the audience catch their breath"
        else:
            return "Keep the momentum going"
    
    def _generate_setlist_notes(
        self,
        songs: List[Dict[str, Any]],
        energy_flow: str
    ) -> List[str]:
        """Generate notes about the setlist."""
        notes = []
        
        notes.append(f"Setlist designed with {energy_flow} energy flow")
        
        total_duration = sum(get_song_duration(s) for s in songs)
        notes.append(f"Total performance time: ~{round(total_duration / 60)} minutes")
        
        high_energy_count = len([s for s in songs if s.get("energy") == "high"])
        notes.append(f"Includes {high_energy_count} high-energy crowd-pleasers")
        
        if energy_flow == "building":
            notes.append("Build energy gradually - save best for last")
        elif energy_flow == "consistent":
            notes.append("Maintain steady energy - keep the crowd engaged")
        else:
            notes.append("Varied energy - create dynamic show experience")
        
        return notes
