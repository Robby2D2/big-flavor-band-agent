"""
Audio Analyzer
Provides audio engineering analysis and improvement suggestions.
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger("audio-analyzer")


class AudioAnalyzer:
    """Analyzer for audio quality and engineering suggestions."""
    
    def __init__(self):
        """Initialize the audio analyzer."""
        logger.info("Audio analyzer initialized")
    
    async def analyze_and_suggest(self, song: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a song and provide engineering suggestions.
        
        Args:
            song: Song metadata
        
        Returns:
            Analysis with improvement suggestions
        """
        quality = song.get("audio_quality", "fair")
        genre = song.get("genre", "")
        mood = song.get("mood", "")
        energy = song.get("energy", "medium")
        tempo = song.get("tempo_bpm", 120)
        
        # Generate quality assessment
        assessment = self._assess_quality(quality)
        
        # Generate genre-specific suggestions
        genre_suggestions = self._get_genre_specific_suggestions(genre)
        
        # Generate mood-based suggestions
        mood_suggestions = self._get_mood_based_suggestions(mood, energy)
        
        # Generate tempo-based suggestions
        tempo_suggestions = self._get_tempo_based_suggestions(tempo)
        
        # Combine all suggestions
        all_suggestions = {
            "mixing": [],
            "mastering": [],
            "effects": [],
            "general": []
        }
        
        for category in all_suggestions:
            all_suggestions[category].extend(genre_suggestions.get(category, []))
            all_suggestions[category].extend(mood_suggestions.get(category, []))
            all_suggestions[category].extend(tempo_suggestions.get(category, []))
        
        # Add quality-specific suggestions
        if quality == "fair":
            all_suggestions["general"].append("Consider re-recording with better microphone placement")
            all_suggestions["general"].append("Room acoustics may need improvement - try adding sound dampening")
        elif quality == "good":
            all_suggestions["general"].append("Recording quality is solid - focus on mixing refinements")
        
        return {
            "song_id": song["id"],
            "song_title": song["title"],
            "current_quality": quality,
            "quality_assessment": assessment,
            "improvement_suggestions": all_suggestions,
            "priority_actions": self._get_priority_actions(quality, genre, mood),
            "estimated_improvement_potential": self._estimate_improvement_potential(quality)
        }
    
    async def compare_quality(self, songs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare audio quality across multiple songs.
        
        Args:
            songs: List of songs to compare
        
        Returns:
            Comparison report
        """
        quality_scores = {
            "excellent": 100,
            "good": 75,
            "fair": 50,
            "poor": 25
        }
        
        comparisons = []
        for song in songs:
            quality = song.get("audio_quality", "fair")
            score = quality_scores.get(quality, 50)
            
            comparisons.append({
                "id": song["id"],
                "title": song["title"],
                "quality": quality,
                "quality_score": score,
                "genre": song.get("genre", ""),
                "recording_date": song.get("recording_date", "")
            })
        
        # Sort by quality score (highest first)
        comparisons.sort(key=lambda x: x["quality_score"], reverse=True)
        
        # Calculate statistics
        avg_score = sum(c["quality_score"] for c in comparisons) / len(comparisons)
        
        # Identify songs needing attention
        needs_attention = [c for c in comparisons if c["quality_score"] < 75]
        
        return {
            "total_songs": len(songs),
            "average_quality_score": round(avg_score, 2),
            "quality_ranking": comparisons,
            "best_quality": comparisons[0] if comparisons else None,
            "needs_attention": needs_attention,
            "recommendations": self._generate_batch_recommendations(comparisons)
        }
    
    def _assess_quality(self, quality: str) -> Dict[str, Any]:
        """Provide detailed quality assessment."""
        assessments = {
            "excellent": {
                "summary": "Professional-grade recording quality",
                "strengths": [
                    "Clear, well-balanced mix",
                    "Good dynamic range",
                    "Minimal background noise",
                    "Professional mastering"
                ],
                "areas_for_refinement": [
                    "Consider A/B testing with reference tracks",
                    "Fine-tune for specific playback environments"
                ]
            },
            "good": {
                "summary": "Solid recording with minor room for improvement",
                "strengths": [
                    "Generally clear sound",
                    "Acceptable balance between instruments",
                    "Minimal technical issues"
                ],
                "areas_for_refinement": [
                    "EQ adjustments could improve clarity",
                    "Compression might help balance dynamics",
                    "Consider professional mastering"
                ]
            },
            "fair": {
                "summary": "Adequate recording but significant improvement possible",
                "strengths": [
                    "Captures the basic performance",
                    "Suitable for demos or practice"
                ],
                "areas_for_refinement": [
                    "Improve recording environment acoustics",
                    "Better microphone placement needed",
                    "Significant mixing and mastering work recommended",
                    "Consider re-recording key parts"
                ]
            },
            "poor": {
                "summary": "Substantial quality issues requiring attention",
                "strengths": [
                    "Preserves the musical ideas"
                ],
                "areas_for_refinement": [
                    "Complete re-recording strongly recommended",
                    "Invest in better recording equipment",
                    "Address room acoustics before recording",
                    "Consider professional recording studio"
                ]
            }
        }
        
        return assessments.get(quality, assessments["fair"])
    
    def _get_genre_specific_suggestions(self, genre: str) -> Dict[str, List[str]]:
        """Get genre-specific engineering suggestions."""
        suggestions = {
            "Rock": {
                "mixing": [
                    "Emphasize guitar presence in 2-4kHz range",
                    "Give bass guitar solid low-end foundation (80-200Hz)",
                    "Drums should be punchy - compress kick and snare"
                ],
                "mastering": [
                    "Target loudness around -10 to -8 LUFS for rock",
                    "Preserve dynamic range in choruses"
                ],
                "effects": [
                    "Use parallel compression on drums for punch",
                    "Consider stereo widening on guitars",
                    "Room reverb can add space without washing out"
                ]
            },
            "Blues": {
                "mixing": [
                    "Keep vocals intimate and upfront",
                    "Guitar tone should be warm - boost lower mids",
                    "Leave dynamics relatively untouched for emotional impact"
                ],
                "mastering": [
                    "Don't over-compress - blues needs dynamics",
                    "Target -12 to -10 LUFS to maintain feel"
                ],
                "effects": [
                    "Subtle reverb on vocals for warmth",
                    "Tape saturation can add vintage character",
                    "Room ambience on instruments for live feel"
                ]
            },
            "Acoustic": {
                "mixing": [
                    "Preserve natural acoustic guitar tone",
                    "Vocals should be clear and present",
                    "Minimal processing to maintain organic sound"
                ],
                "mastering": [
                    "Light touch on compression",
                    "Target -14 to -12 LUFS for natural dynamics"
                ],
                "effects": [
                    "Natural room reverb works well",
                    "Avoid heavy effects - keep it pure",
                    "Gentle EQ to enhance natural resonance"
                ]
            }
        }
        
        return suggestions.get(genre, {
            "mixing": ["Focus on balanced frequency spectrum", "Ensure clarity of lead instruments/vocals"],
            "mastering": ["Standard mastering approach for genre"],
            "effects": ["Use effects tastefully to support the song"]
        })
    
    def _get_mood_based_suggestions(
        self,
        mood: str,
        energy: str
    ) -> Dict[str, List[str]]:
        """Get mood and energy-based suggestions."""
        suggestions = {"mixing": [], "effects": [], "general": []}
        
        if mood == "upbeat" or mood == "energetic":
            suggestions["mixing"].append("Boost upper-mid frequencies for brightness and excitement")
            suggestions["effects"].append("Consider stereo enhancement for wider sound")
            suggestions["general"].append("Tight, punchy mix maintains energy")
        
        elif mood == "melancholic" or mood == "emotional":
            suggestions["mixing"].append("Warm low-mids create intimate, emotional feeling")
            suggestions["effects"].append("Longer reverb tails add space and emotion")
            suggestions["general"].append("Don't over-compress - let dynamics tell the story")
        
        elif mood == "relaxed" or mood == "mellow":
            suggestions["mixing"].append("Smooth, balanced mix without harsh frequencies")
            suggestions["effects"].append("Gentle, natural reverb creates comfortable space")
            suggestions["general"].append("Subtle approach - avoid aggressive processing")
        
        if energy == "high":
            suggestions["mixing"].append("Emphasize attack on drums and bass for impact")
            suggestions["general"].append("Ensure mix has plenty of headroom for dynamics")
        
        elif energy == "low":
            suggestions["mixing"].append("Focus on clarity and space rather than punch")
            suggestions["general"].append("Gentle compression maintains intimacy")
        
        return suggestions
    
    def _get_tempo_based_suggestions(self, tempo: float) -> Dict[str, List[str]]:
        """Get tempo-specific suggestions."""
        suggestions = {"mixing": [], "effects": []}
        
        if tempo < 90:  # Slow tempo
            suggestions["mixing"].append("Longer decay times work well with slow tempo")
            suggestions["effects"].append("Extended reverb/delay can fill space between notes")
        
        elif tempo > 140:  # Fast tempo
            suggestions["mixing"].append("Tighter gating and shorter effects for clarity")
            suggestions["effects"].append("Shorter reverb times prevent muddiness at fast tempo")
        
        else:  # Medium tempo
            suggestions["mixing"].append("Standard mixing approach works well")
        
        return suggestions
    
    def _get_priority_actions(
        self,
        quality: str,
        genre: str,
        mood: str
    ) -> List[str]:
        """Get prioritized action items."""
        priorities = []
        
        if quality == "fair" or quality == "poor":
            priorities.append("1. Address recording quality - improve room acoustics and mic placement")
            priorities.append("2. Re-record if possible, or apply noise reduction carefully")
            priorities.append("3. Focus on basic EQ to improve clarity")
        else:
            priorities.append("1. Fine-tune EQ for genre-specific tonal balance")
            priorities.append("2. Apply appropriate compression for dynamics")
            priorities.append("3. Add effects and ambience tastefully")
        
        priorities.append(f"4. Reference mix against professional {genre} tracks")
        priorities.append("5. Master for consistent loudness across your library")
        
        return priorities
    
    def _estimate_improvement_potential(self, current_quality: str) -> Dict[str, Any]:
        """Estimate how much quality improvement is possible."""
        potential_map = {
            "excellent": {
                "percentage": 5,
                "description": "Minimal - already at high quality",
                "effort": "low"
            },
            "good": {
                "percentage": 25,
                "description": "Moderate - refinements can add polish",
                "effort": "medium"
            },
            "fair": {
                "percentage": 50,
                "description": "Significant - substantial improvements possible",
                "effort": "high"
            },
            "poor": {
                "percentage": 80,
                "description": "Major - requires complete rework or re-recording",
                "effort": "very high"
            }
        }
        
        return potential_map.get(current_quality, potential_map["fair"])
    
    def _generate_batch_recommendations(
        self,
        comparisons: List[Dict[str, Any]]
    ) -> List[str]:
        """Generate recommendations for batch of songs."""
        recommendations = []
        
        # Check if there's consistency across library
        qualities = [c["quality"] for c in comparisons]
        if len(set(qualities)) > 2:
            recommendations.append("Quality varies significantly - consider standardizing recording process")
        
        # Check for trends over time
        dated_songs = [c for c in comparisons if c.get("recording_date")]
        if len(dated_songs) > 1:
            recommendations.append("Review newer recordings vs older ones - are you improving?")
        
        # Low quality songs
        poor_quality = [c for c in comparisons if c["quality_score"] < 60]
        if poor_quality:
            recommendations.append(f"Consider re-recording {len(poor_quality)} lower-quality songs")
        
        # Genre-specific
        genres = set(c["genre"] for c in comparisons)
        if len(genres) > 1:
            recommendations.append("Develop genre-specific recording templates for consistency")
        
        recommendations.append("Build a reference playlist of professional tracks to compare against")
        recommendations.append("Consider investing in acoustic treatment for recording space")
        
        return recommendations
