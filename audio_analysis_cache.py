"""
Audio Analysis Cache Module
Analyzes MP3 files to extract BPM, genre, and other audio features.
Stores results in a local cache to avoid re-analyzing unchanged files.
"""

import json
import logging
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("audio-analysis-cache")

# Flag to track if librosa is available
LIBROSA_AVAILABLE = False
try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
    logger.info("Librosa loaded successfully for audio analysis")
except ImportError:
    logger.warning("Librosa not available. Audio analysis will be limited. Install with: pip install librosa")


class AudioAnalysisCache:
    """Manages audio analysis with local caching."""
    
    def __init__(self, cache_dir: str = ".audio_cache"):
        """
        Initialize the audio analysis cache.
        
        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "analysis_cache.json"
        self.cache_data = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
                return {}
        return {}
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def _get_file_hash(self, file_path: str) -> Optional[str]:
        """
        Get a hash of the file for change detection.
        Uses file size and modification time for efficiency.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Hash string or None if file doesn't exist
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            stat = path.stat()
            # Combine size and mtime for a quick fingerprint
            fingerprint = f"{stat.st_size}_{stat.st_mtime}"
            return hashlib.md5(fingerprint.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Error getting file hash: {e}")
            return None
    
    def _get_cache_key(self, audio_url: str) -> str:
        """Generate cache key from audio URL."""
        return hashlib.md5(audio_url.encode()).hexdigest()
    
    def get_cached_analysis(self, audio_url: str, file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get cached analysis if available and still valid.
        
        Args:
            audio_url: URL of the audio file
            file_path: Local path to the audio file (for change detection)
            
        Returns:
            Cached analysis or None if not available/invalid
        """
        cache_key = self._get_cache_key(audio_url)
        
        if cache_key not in self.cache_data:
            return None
        
        cached = self.cache_data[cache_key]
        
        # If we have a local file, check if it has changed
        if file_path:
            file_hash = self._get_file_hash(file_path)
            if file_hash and cached.get('file_hash') != file_hash:
                logger.info(f"File changed, invalidating cache for {audio_url}")
                return None
        
        logger.info(f"Using cached analysis for {audio_url}")
        return cached.get('analysis')
    
    def save_analysis(self, audio_url: str, analysis: Dict[str, Any], file_path: Optional[str] = None):
        """
        Save analysis to cache.
        
        Args:
            audio_url: URL of the audio file
            analysis: Analysis results to cache
            file_path: Local path to the audio file
        """
        cache_key = self._get_cache_key(audio_url)
        
        cache_entry = {
            'analysis': analysis,
            'timestamp': datetime.now().isoformat(),
            'audio_url': audio_url
        }
        
        if file_path:
            cache_entry['file_hash'] = self._get_file_hash(file_path)
            cache_entry['file_path'] = str(file_path)
        
        self.cache_data[cache_key] = cache_entry
        self._save_cache()
        logger.info(f"Saved analysis to cache for {audio_url}")
    
    def analyze_audio_file(self, file_path: str, audio_url: str = "") -> Dict[str, Any]:
        """
        Analyze an audio file to extract BPM, genre hints, and other features.
        
        Args:
            file_path: Path to the audio file
            audio_url: URL of the audio file (for caching)
            
        Returns:
            Dictionary with analysis results
        """
        # Check cache first
        if audio_url:
            cached = self.get_cached_analysis(audio_url, file_path)
            if cached:
                return cached
        
        # Perform analysis
        analysis = self._perform_analysis(file_path)
        
        # Save to cache
        if audio_url:
            self.save_analysis(audio_url, analysis, file_path)
        
        return analysis
    
    def _perform_analysis(self, file_path: str) -> Dict[str, Any]:
        """
        Perform actual audio analysis using librosa.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary with analysis results
        """
        if not LIBROSA_AVAILABLE:
            logger.warning(f"Cannot analyze {file_path}: librosa not available")
            return {
                'bpm': None,
                'genre_hints': [],
                'key': None,
                'energy': 'medium',
                'duration_seconds': None,
                'error': 'librosa_not_installed'
            }
        
        try:
            logger.info(f"Analyzing audio file: {file_path}")
            
            # Load audio file
            y, sr = librosa.load(file_path, sr=None, mono=True)
            
            # Calculate duration
            duration = librosa.get_duration(y=y, sr=sr)
            
            # Extract tempo (BPM)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
            bpm = float(tempo)
            
            # Extract spectral features for genre hints
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            zero_crossing_rate = librosa.feature.zero_crossing_rate(y)[0]
            
            # Calculate energy (RMS)
            rms = librosa.feature.rms(y=y)[0]
            avg_energy = float(np.mean(rms))
            
            # Categorize energy level
            if avg_energy < 0.02:
                energy_level = 'low'
            elif avg_energy < 0.05:
                energy_level = 'medium'
            else:
                energy_level = 'high'
            
            # Estimate key using chroma features
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            key_index = int(np.argmax(np.sum(chroma, axis=1)))
            key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            estimated_key = key_names[key_index]
            
            # Genre hints based on audio characteristics
            genre_hints = self._infer_genre_from_features(
                bpm=bpm,
                spectral_centroid=float(np.mean(spectral_centroids)),
                spectral_rolloff=float(np.mean(spectral_rolloff)),
                zero_crossing_rate=float(np.mean(zero_crossing_rate)),
                energy=avg_energy
            )
            
            analysis = {
                'bpm': round(bpm, 1),
                'genre_hints': genre_hints,
                'key': estimated_key,
                'energy': energy_level,
                'duration_seconds': round(duration, 1),
                'spectral_features': {
                    'centroid': float(np.mean(spectral_centroids)),
                    'rolloff': float(np.mean(spectral_rolloff)),
                    'zero_crossing_rate': float(np.mean(zero_crossing_rate))
                },
                'analysis_timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"Analysis complete: BPM={bpm:.1f}, Key={estimated_key}, Energy={energy_level}")
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing audio file {file_path}: {e}")
            return {
                'bpm': None,
                'genre_hints': [],
                'key': None,
                'energy': 'medium',
                'duration_seconds': None,
                'error': str(e)
            }
    
    def _infer_genre_from_features(
        self,
        bpm: float,
        spectral_centroid: float,
        spectral_rolloff: float,
        zero_crossing_rate: float,
        energy: float
    ) -> list[str]:
        """
        Infer possible genres from audio features.
        This is a heuristic approach and not definitive.
        
        Args:
            bpm: Beats per minute
            spectral_centroid: Average spectral centroid
            spectral_rolloff: Average spectral rolloff
            zero_crossing_rate: Average zero crossing rate
            energy: Average RMS energy
            
        Returns:
            List of possible genre hints
        """
        hints = []
        
        # BPM-based hints
        if 60 <= bpm <= 80:
            hints.extend(['Blues', 'Ballad', 'Soul'])
        elif 80 <= bpm <= 110:
            hints.extend(['Rock', 'Alternative', 'Folk'])
        elif 110 <= bpm <= 140:
            hints.extend(['Rock', 'Pop', 'Indie'])
        elif 140 <= bpm <= 180:
            hints.extend(['Punk', 'Metal', 'Hard Rock'])
        
        # Spectral features for brightness/darkness
        if spectral_centroid > 2000:
            # Brighter, could be more energetic genres
            if 'Pop' not in hints:
                hints.append('Pop')
        
        # Zero crossing rate for distortion/roughness
        if zero_crossing_rate > 0.1:
            # Higher distortion, suggests rock/metal
            if 'Rock' not in hints:
                hints.append('Rock')
        
        # Energy-based hints
        if energy > 0.05:
            if 'Energetic' not in hints:
                hints.append('Energetic')
        elif energy < 0.02:
            if 'Acoustic' not in hints:
                hints.append('Acoustic')
        
        # Remove duplicates while preserving order
        seen = set()
        unique_hints = []
        for hint in hints:
            if hint not in seen:
                seen.add(hint)
                unique_hints.append(hint)
        
        return unique_hints[:3]  # Return top 3 hints
    
    def analyze_from_url(self, audio_url: str, download_func=None) -> Dict[str, Any]:
        """
        Analyze audio from URL, downloading if necessary.
        
        Args:
            audio_url: URL of the audio file
            download_func: Optional function to download the file
            
        Returns:
            Analysis results
        """
        # Check cache first
        cached = self.get_cached_analysis(audio_url)
        if cached:
            return cached
        
        # Would need to download the file first
        # This is a placeholder for future implementation
        logger.warning(f"Direct URL analysis not implemented. Need to download {audio_url} first.")
        return {
            'bpm': None,
            'genre_hints': [],
            'key': None,
            'energy': 'medium',
            'duration_seconds': None,
            'error': 'download_not_implemented'
        }
    
    def clear_cache(self):
        """Clear all cached analysis data."""
        self.cache_data = {}
        self._save_cache()
        logger.info("Cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache."""
        return {
            'total_entries': len(self.cache_data),
            'cache_file': str(self.cache_file),
            'cache_size_bytes': self.cache_file.stat().st_size if self.cache_file.exists() else 0
        }
