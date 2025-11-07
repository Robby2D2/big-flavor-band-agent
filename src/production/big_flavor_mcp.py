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
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import from database package
from database import DatabaseManager

# Import librosa for audio analysis
try:
    import librosa
    import numpy as np
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-mcp")


class BigFlavorMCPServer:
    """MCP Server for Big Flavor audio production and analysis operations."""
    
    def __init__(self, enable_audio_analysis: bool = True):
        self.app = Server("big-flavor-production-server")
        self.enable_audio_analysis = enable_audio_analysis
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
                # EDITING TOOLS - for processing raw recordings
                Tool(
                    name="trim_silence",
                    description="Remove silence from the beginning and end of audio. Perfect for cleaning up raw recordings.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to trim"
                            },
                            "threshold_db": {
                                "type": "number",
                                "description": "Silence threshold in dB (default: -40)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for trimmed file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="reduce_noise",
                    description="Remove background noise, hum, hiss, and feedback from audio recordings",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to process"
                            },
                            "noise_profile_duration": {
                                "type": "number",
                                "description": "Duration in seconds to sample for noise profile (default: 1.0)"
                            },
                            "reduction_strength": {
                                "type": "number",
                                "description": "Noise reduction strength 0-1 (default: 0.7)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for cleaned file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="correct_pitch",
                    description="Apply pitch correction to fix wrong notes or tuning issues",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to correct"
                            },
                            "semitones": {
                                "type": "number",
                                "description": "Semitones to shift (positive or negative, default: 0 for auto-tune)"
                            },
                            "auto_tune": {
                                "type": "boolean",
                                "description": "Enable automatic pitch correction to nearest notes (default: false)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for corrected file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="normalize_audio",
                    description="Normalize audio levels and apply compression for consistent volume",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to normalize"
                            },
                            "target_level_db": {
                                "type": "number",
                                "description": "Target peak level in dB (default: -3)"
                            },
                            "apply_compression": {
                                "type": "boolean",
                                "description": "Apply compression for dynamic range control (default: true)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for normalized file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="apply_eq",
                    description="Apply equalizer filters to shape the sound (remove mud, add clarity, etc.)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to EQ"
                            },
                            "high_pass_freq": {
                                "type": "number",
                                "description": "High-pass filter frequency in Hz (removes low rumble, default: 30)"
                            },
                            "low_pass_freq": {
                                "type": "number",
                                "description": "Low-pass filter frequency in Hz (removes high noise, optional)"
                            },
                            "boost_freq": {
                                "type": "number",
                                "description": "Frequency in Hz to boost (optional)"
                            },
                            "boost_db": {
                                "type": "number",
                                "description": "Boost amount in dB (default: 3)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for EQ'd file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
                Tool(
                    name="remove_artifacts",
                    description="Detect and remove clicks, pops, and digital glitches from audio",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to clean"
                            },
                            "sensitivity": {
                                "type": "number",
                                "description": "Detection sensitivity 0-1 (default: 0.5)"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for cleaned file"
                            }
                        },
                        "required": ["file_path", "output_path"]
                    }
                ),
            ]
        
        @self.app.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            """Handle tool execution requests."""
            try:
                if name == "analyze_audio":
                    result = await self.analyze_audio(arguments["file_path"])
                elif name == "match_tempo":
                    result = await self.match_tempo(
                        arguments["file_path"],
                        arguments["target_bpm"],
                        arguments["output_path"]
                    )
                elif name == "create_transition":
                    result = await self.create_transition(
                        arguments["song1_path"],
                        arguments["song2_path"],
                        arguments.get("transition_duration", 8),
                        arguments["output_path"]
                    )
                elif name == "apply_mastering":
                    result = await self.apply_mastering(
                        arguments["file_path"],
                        arguments.get("target_loudness", -14.0),
                        arguments["output_path"]
                    )
                elif name == "get_audio_cache_stats":
                    result = await self.get_audio_cache_stats()
                # EDITING TOOLS
                elif name == "trim_silence":
                    result = await self.trim_silence(
                        arguments["file_path"],
                        arguments.get("threshold_db", -40),
                        arguments["output_path"]
                    )
                elif name == "reduce_noise":
                    result = await self.reduce_noise(
                        arguments["file_path"],
                        arguments.get("noise_profile_duration", 1.0),
                        arguments.get("reduction_strength", 0.7),
                        arguments["output_path"]
                    )
                elif name == "correct_pitch":
                    result = await self.correct_pitch(
                        arguments["file_path"],
                        arguments.get("semitones", 0),
                        arguments.get("auto_tune", False),
                        arguments["output_path"]
                    )
                elif name == "normalize_audio":
                    result = await self.normalize_audio(
                        arguments["file_path"],
                        arguments.get("target_level_db", -3),
                        arguments.get("apply_compression", True),
                        arguments["output_path"]
                    )
                elif name == "apply_eq":
                    result = await self.apply_eq(
                        arguments["file_path"],
                        arguments.get("high_pass_freq", 30),
                        arguments.get("low_pass_freq"),
                        arguments.get("boost_freq"),
                        arguments.get("boost_db", 3),
                        arguments["output_path"]
                    )
                elif name == "remove_artifacts":
                    result = await self.remove_artifacts(
                        arguments["file_path"],
                        arguments.get("sensitivity", 0.5),
                        arguments["output_path"]
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
    
    async def analyze_audio(self, file_path: str) -> dict:
        """
        Analyze an audio file to extract tempo, key, beats, and other features.
        Uses PostgreSQL audio_analysis_cache table for caching.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Analysis results including BPM, key, energy, etc.
        """
        if not self.enable_audio_analysis or not LIBROSA_AVAILABLE:
            return {
                "error": "Audio analysis is disabled or librosa not available",
                "message": "Enable audio analysis and install librosa"
            }
        
        try:
            # Check if analysis is cached in database
            from pathlib import Path
            file_path_obj = Path(file_path)
            file_hash = self._get_file_hash(file_path)
            
            # Check database cache
            cached_analysis = await self._get_cached_analysis(file_path, file_hash)
            if cached_analysis:
                logger.info(f"Using cached analysis for {file_path}")
                return {
                    "file_path": file_path,
                    "analysis": cached_analysis,
                    "status": "success",
                    "cached": True
                }
            
            # Perform fresh analysis
            logger.info(f"Analyzing audio file: {file_path}")
            analysis = await self._perform_audio_analysis(file_path)
            
            # Save to database cache
            await self._save_analysis_to_cache(file_path, file_hash, analysis)
            
            return {
                "file_path": file_path,
                "analysis": analysis,
                "status": "success",
                "cached": False
            }
        except Exception as e:
            logger.error(f"Error analyzing audio file: {e}")
            return {
                "error": str(e),
                "file_path": file_path,
                "status": "error"
            }
    
    def _get_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of a file."""
        import hashlib
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    
    async def _get_cached_analysis(self, file_path: str, file_hash: str) -> Optional[dict]:
        """Get cached analysis from database."""
        if not self.db_manager:
            return None
        
        try:
            query = """
                SELECT analysis_data 
                FROM audio_analysis_cache 
                WHERE file_path = $1 AND file_hash = $2
            """
            async with self.db_manager.pool.acquire() as conn:
                row = await conn.fetchrow(query, file_path, file_hash)
                if row:
                    return row['analysis_data']
        except Exception as e:
            logger.warning(f"Error checking cache: {e}")
        return None
    
    async def _save_analysis_to_cache(self, file_path: str, file_hash: str, analysis: dict):
        """Save analysis to database cache."""
        if not self.db_manager:
            return
        
        try:
            query = """
                INSERT INTO audio_analysis_cache (file_path, file_hash, analysis_data, analyzed_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (file_path) 
                DO UPDATE SET 
                    file_hash = EXCLUDED.file_hash,
                    analysis_data = EXCLUDED.analysis_data,
                    analyzed_at = EXCLUDED.analyzed_at
            """
            async with self.db_manager.pool.acquire() as conn:
                await conn.execute(query, file_path, file_hash, analysis)
            logger.info(f"Saved analysis to cache for {file_path}")
        except Exception as e:
            logger.warning(f"Error saving to cache: {e}")
    
    async def _perform_audio_analysis(self, file_path: str) -> dict:
        """Perform actual audio analysis using librosa."""
        import librosa
        import numpy as np
        from datetime import datetime
        
        # Load audio file
        y, sr = librosa.load(file_path, sr=None, mono=True)
        
        # Calculate duration
        duration = librosa.get_duration(y=y, sr=sr)
        
        # Extract tempo (BPM)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo)
        
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
        
        # Extract spectral features
        spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        zero_crossing_rate = librosa.feature.zero_crossing_rate(y)[0]
        
        analysis = {
            'bpm': round(bpm, 1),
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
    
    async def match_tempo(self, file_path: str, target_bpm: float, output_path: str) -> dict:
        """
        Time-stretch audio to match a specific BPM without changing pitch.
        
        Args:
            file_path: Path to input audio file
            target_bpm: Target tempo in BPM
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            
            # Load audio
            y, sr = librosa.load(file_path)
            
            # Detect current tempo
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            current_bpm = tempo if isinstance(tempo, float) else tempo[0]
            
            # Calculate stretch ratio
            stretch_ratio = target_bpm / current_bpm
            
            # Time-stretch audio
            y_stretched = librosa.effects.time_stretch(y, rate=stretch_ratio)
            
            # Save output
            sf.write(output_path, y_stretched, sr)
            
            logger.info(f"Tempo matched: {current_bpm:.1f} BPM → {target_bpm:.1f} BPM")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_bpm": round(current_bpm, 1),
                "target_bpm": target_bpm,
                "stretch_ratio": round(stretch_ratio, 3)
            }
            
        except Exception as e:
            logger.error(f"Error matching tempo: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def create_transition(
        self, 
        song1_path: str, 
        song2_path: str, 
        transition_duration: float,
        output_path: str
    ) -> dict:
        """
        Create a beat-matched DJ transition between two songs.
        
        Args:
            song1_path: Path to first song
            song2_path: Path to second song
            transition_duration: Duration of transition in seconds
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            
            # Load both songs
            y1, sr1 = librosa.load(song1_path)
            y2, sr2 = librosa.load(song2_path)
            
            # Resample if sample rates differ
            if sr1 != sr2:
                y2 = librosa.resample(y2, orig_sr=sr2, target_sr=sr1)
                sr = sr1
            else:
                sr = sr1
            
            # Detect tempos
            tempo1, beats1 = librosa.beat.beat_track(y=y1, sr=sr)
            tempo2, beats2 = librosa.beat.beat_track(y=y2, sr=sr)
            
            bpm1 = tempo1 if isinstance(tempo1, float) else tempo1[0]
            bpm2 = tempo2 if isinstance(tempo2, float) else tempo2[0]
            
            # Time-stretch song2 to match song1's tempo
            if abs(bpm1 - bpm2) > 1:
                stretch_ratio = bpm1 / bpm2
                y2 = librosa.effects.time_stretch(y2, rate=stretch_ratio)
            
            # Calculate transition length in samples
            transition_samples = int(transition_duration * sr)
            
            # Get ending of song1 and beginning of song2
            song1_end = y1[-transition_samples:]
            song2_start = y2[:transition_samples]
            
            # Create crossfade
            fade_out = np.linspace(1, 0, transition_samples)
            fade_in = np.linspace(0, 1, transition_samples)
            
            transition = song1_end * fade_out + song2_start * fade_in
            
            # Concatenate: song1 (minus transition) + transition + song2 (minus transition)
            output = np.concatenate([
                y1[:-transition_samples],
                transition,
                y2[transition_samples:]
            ])
            
            # Save output
            sf.write(output_path, output, sr)
            
            logger.info(f"Created transition: {Path(song1_path).name} → {Path(song2_path).name}")
            
            return {
                "status": "success",
                "song1": song1_path,
                "song2": song2_path,
                "output_file": output_path,
                "transition_duration": transition_duration,
                "song1_bpm": round(bpm1, 1),
                "song2_bpm": round(bpm2, 1),
                "tempo_adjusted": abs(bpm1 - bpm2) > 1
            }
            
        except Exception as e:
            logger.error(f"Error creating transition: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def apply_mastering(
        self, 
        file_path: str, 
        target_loudness: float,
        output_path: str
    ) -> dict:
        """
        Apply professional mastering to make audio louder and more polished.
        
        Args:
            file_path: Path to input audio file
            target_loudness: Target LUFS loudness (default: -14.0)
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            
            # Apply high-pass filter to remove rumble
            sos = signal.butter(4, 30, 'hp', fs=sr, output='sos')
            y_filtered = signal.sosfilt(sos, y)
            
            # Apply gentle compression (simplified)
            threshold = 0.3
            ratio = 4
            y_compressed = np.where(
                np.abs(y_filtered) > threshold,
                threshold + (y_filtered - threshold * np.sign(y_filtered)) / ratio,
                y_filtered
            )
            
            # Calculate current RMS level
            rms = np.sqrt(np.mean(y_compressed**2))
            
            # Target RMS based on LUFS (simplified conversion)
            # LUFS -14 ≈ RMS 0.25, LUFS -16 ≈ RMS 0.2
            target_rms = 10 ** ((target_loudness + 15) / 20)
            
            # Apply gain to reach target
            if rms > 0:
                gain = target_rms / rms
                # Limit gain to prevent clipping
                gain = min(gain, 0.95 / np.max(np.abs(y_compressed)))
                y_mastered = y_compressed * gain
            else:
                y_mastered = y_compressed
            
            # Apply soft limiter
            y_limited = np.tanh(y_mastered * 1.2) * 0.95
            
            # Save output
            sf.write(output_path, y_limited, sr)
            
            # Calculate final RMS
            final_rms = np.sqrt(np.mean(y_limited**2))
            final_lufs = 20 * np.log10(final_rms) - 15
            
            logger.info(f"Mastering complete: {file_path} → {output_path}")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "target_loudness_lufs": target_loudness,
                "actual_loudness_lufs": round(final_lufs, 1),
                "gain_applied_db": round(20 * np.log10(gain), 1) if rms > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error applying mastering: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def get_audio_cache_stats(self) -> dict:
        """Get statistics about the audio analysis cache from database."""
        if not self.enable_audio_analysis:
            return {
                "error": "Audio analysis is disabled",
                "message": "Enable audio analysis when initializing the server"
            }
        
        if not self.db_manager:
            return {"error": "Database not initialized"}
        
        try:
            query = """
                SELECT 
                    COUNT(*) as total_cached,
                    MAX(analyzed_at) as last_analysis
                FROM audio_analysis_cache
            """
            async with self.db_manager.pool.acquire() as conn:
                row = await conn.fetchrow(query)
                return {
                    "total_cached_analyses": row['total_cached'],
                    "last_analysis": row['last_analysis'].isoformat() if row['last_analysis'] else None,
                    "cache_type": "postgresql"
                }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}
    
    # ==================== EDITING TOOLS ====================
    # Tools for processing raw recordings into production-ready audio
    
    async def trim_silence(
        self,
        file_path: str,
        threshold_db: float,
        output_path: str
    ) -> dict:
        """
        Remove silence from beginning and end of audio.
        
        Args:
            file_path: Path to input audio file
            threshold_db: Silence threshold in dB (default: -40)
            output_path: Path for output file
            
        Returns:
            Operation result with trimming statistics
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            original_duration = len(y) / sr
            
            # Convert threshold from dB to amplitude
            threshold_amplitude = librosa.db_to_amplitude(threshold_db)
            
            # Find non-silent intervals
            non_silent = librosa.effects.split(y, top_db=-threshold_db)
            
            if len(non_silent) == 0:
                return {
                    "status": "error",
                    "error": "No non-silent audio found",
                    "input_file": file_path
                }
            
            # Get the first and last non-silent intervals
            start_sample = non_silent[0][0]
            end_sample = non_silent[-1][1]
            
            # Trim audio
            y_trimmed = y[start_sample:end_sample]
            trimmed_duration = len(y_trimmed) / sr
            
            # Save output
            sf.write(output_path, y_trimmed, sr)
            
            logger.info(f"Trimmed silence: {original_duration:.2f}s → {trimmed_duration:.2f}s")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_duration_seconds": round(original_duration, 2),
                "trimmed_duration_seconds": round(trimmed_duration, 2),
                "removed_seconds": round(original_duration - trimmed_duration, 2),
                "threshold_db": threshold_db
            }
            
        except Exception as e:
            logger.error(f"Error trimming silence: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def reduce_noise(
        self,
        file_path: str,
        noise_profile_duration: float,
        reduction_strength: float,
        output_path: str
    ) -> dict:
        """
        Remove background noise, hum, hiss, and feedback.
        Uses spectral gating technique.
        
        Args:
            file_path: Path to input audio file
            noise_profile_duration: Duration in seconds to sample noise (default: 1.0)
            reduction_strength: Reduction strength 0-1 (default: 0.7)
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            
            # Get noise profile from beginning
            noise_samples = int(noise_profile_duration * sr)
            noise_profile = y[:noise_samples]
            
            # Compute STFT
            D = librosa.stft(y)
            D_noise = librosa.stft(noise_profile)
            
            # Estimate noise spectrum (average magnitude)
            noise_mag = np.abs(D_noise).mean(axis=1, keepdims=True)
            
            # Get magnitude and phase
            mag = np.abs(D)
            phase = np.angle(D)
            
            # Spectral gating: reduce magnitude where it's close to noise level
            # Scale noise threshold by reduction strength
            noise_threshold = noise_mag * (2 - reduction_strength)
            
            # Apply soft gating
            mask = np.maximum(0, 1 - (noise_threshold / (mag + 1e-10)))
            mag_reduced = mag * mask
            
            # Reconstruct signal
            D_reduced = mag_reduced * np.exp(1j * phase)
            y_denoised = librosa.istft(D_reduced)
            
            # Apply high-pass filter to remove low-frequency rumble
            sos = signal.butter(4, 60, 'hp', fs=sr, output='sos')
            y_filtered = signal.sosfilt(sos, y_denoised)
            
            # Trim to original length if needed
            if len(y_filtered) > len(y):
                y_filtered = y_filtered[:len(y)]
            elif len(y_filtered) < len(y):
                y_filtered = np.pad(y_filtered, (0, len(y) - len(y_filtered)))
            
            # Save output
            sf.write(output_path, y_filtered, sr)
            
            # Calculate noise reduction amount
            original_noise = np.std(y[:noise_samples])
            reduced_noise = np.std(y_filtered[:noise_samples])
            noise_reduction_db = 20 * np.log10(original_noise / (reduced_noise + 1e-10))
            
            logger.info(f"Noise reduction applied: {noise_reduction_db:.1f} dB reduction")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "reduction_strength": reduction_strength,
                "noise_reduction_db": round(noise_reduction_db, 1),
                "noise_profile_duration": noise_profile_duration
            }
            
        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def correct_pitch(
        self,
        file_path: str,
        semitones: float,
        auto_tune: bool,
        output_path: str
    ) -> dict:
        """
        Apply pitch correction to fix tuning or wrong notes.
        
        Args:
            file_path: Path to input audio file
            semitones: Semitones to shift (0 for auto-tune only)
            auto_tune: Enable automatic pitch correction
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            
            if auto_tune:
                # Extract pitch using piptrack
                pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
                
                # Get dominant pitch over time
                pitch_track = []
                for t in range(pitches.shape[1]):
                    index = magnitudes[:, t].argmax()
                    pitch = pitches[index, t]
                    if pitch > 0:
                        pitch_track.append(pitch)
                
                if not pitch_track:
                    return {
                        "status": "error",
                        "error": "Could not detect pitch in audio",
                        "input_file": file_path
                    }
                
                # Calculate average pitch
                avg_pitch = np.median(pitch_track)
                
                # Find nearest MIDI note
                midi_note = librosa.hz_to_midi(avg_pitch)
                nearest_midi = round(midi_note)
                
                # Calculate correction needed
                correction_semitones = nearest_midi - midi_note + semitones
                
                logger.info(f"Auto-tune: {avg_pitch:.1f}Hz → MIDI {nearest_midi} ({correction_semitones:+.2f} semitones)")
            else:
                correction_semitones = semitones
            
            # Apply pitch shift
            if abs(correction_semitones) > 0.01:
                y_corrected = librosa.effects.pitch_shift(
                    y, 
                    sr=sr, 
                    n_steps=correction_semitones
                )
            else:
                y_corrected = y
                logger.info("No pitch correction needed")
            
            # Save output
            sf.write(output_path, y_corrected, sr)
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "semitones_shift": round(correction_semitones, 2),
                "auto_tune_enabled": auto_tune
            }
            
        except Exception as e:
            logger.error(f"Error correcting pitch: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def normalize_audio(
        self,
        file_path: str,
        target_level_db: float,
        apply_compression: bool,
        output_path: str
    ) -> dict:
        """
        Normalize audio levels and optionally apply compression.
        
        Args:
            file_path: Path to input audio file
            target_level_db: Target peak level in dB (default: -3)
            apply_compression: Apply dynamic range compression
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            
            # Calculate current peak level
            current_peak = np.max(np.abs(y))
            current_peak_db = 20 * np.log10(current_peak) if current_peak > 0 else -np.inf
            
            if apply_compression:
                # Apply gentle compression
                threshold = 0.4
                ratio = 3.0
                
                # Soft-knee compression
                y_compressed = np.where(
                    np.abs(y) > threshold,
                    threshold + (y - threshold * np.sign(y)) / ratio,
                    y
                )
            else:
                y_compressed = y
            
            # Normalize to target level
            target_amplitude = librosa.db_to_amplitude(target_level_db)
            peak_after_compression = np.max(np.abs(y_compressed))
            
            if peak_after_compression > 0:
                gain = target_amplitude / peak_after_compression
                y_normalized = y_compressed * gain
            else:
                y_normalized = y_compressed
            
            # Ensure no clipping
            y_normalized = np.clip(y_normalized, -1.0, 1.0)
            
            # Save output
            sf.write(output_path, y_normalized, sr)
            
            final_peak_db = 20 * np.log10(np.max(np.abs(y_normalized)))
            gain_applied_db = final_peak_db - current_peak_db
            
            logger.info(f"Normalized: {current_peak_db:.1f}dB → {final_peak_db:.1f}dB")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_peak_db": round(current_peak_db, 1),
                "target_peak_db": target_level_db,
                "final_peak_db": round(final_peak_db, 1),
                "gain_applied_db": round(gain_applied_db, 1),
                "compression_applied": apply_compression
            }
            
        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def apply_eq(
        self,
        file_path: str,
        high_pass_freq: float,
        low_pass_freq: Optional[float],
        boost_freq: Optional[float],
        boost_db: float,
        output_path: str
    ) -> dict:
        """
        Apply equalizer filters to shape the sound.
        
        Args:
            file_path: Path to input audio file
            high_pass_freq: High-pass filter frequency in Hz
            low_pass_freq: Optional low-pass filter frequency in Hz
            boost_freq: Optional frequency to boost
            boost_db: Boost amount in dB
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            y_filtered = y.copy()
            
            filters_applied = []
            
            # Apply high-pass filter (remove low rumble)
            if high_pass_freq and high_pass_freq > 0:
                sos = signal.butter(4, high_pass_freq, 'hp', fs=sr, output='sos')
                y_filtered = signal.sosfilt(sos, y_filtered)
                filters_applied.append(f"High-pass @ {high_pass_freq}Hz")
            
            # Apply low-pass filter (remove high noise)
            if low_pass_freq and low_pass_freq > 0:
                sos = signal.butter(4, low_pass_freq, 'lp', fs=sr, output='sos')
                y_filtered = signal.sosfilt(sos, y_filtered)
                filters_applied.append(f"Low-pass @ {low_pass_freq}Hz")
            
            # Apply parametric boost
            if boost_freq and boost_freq > 0:
                # Create a peaking EQ filter
                Q = 1.5  # Quality factor (bandwidth)
                gain_linear = librosa.db_to_amplitude(boost_db)
                
                # Design peaking filter
                # Note: scipy doesn't have direct peaking filter, so we use bandpass
                # with gain adjustment as approximation
                sos = signal.butter(2, [boost_freq / 1.5, boost_freq * 1.5], 'bp', fs=sr, output='sos')
                y_boost = signal.sosfilt(sos, y_filtered)
                
                # Mix boosted signal
                boost_amount = (gain_linear - 1) * 0.5  # Scale the boost
                y_filtered = y_filtered + y_boost * boost_amount
                filters_applied.append(f"Boost {boost_db}dB @ {boost_freq}Hz")
            
            # Normalize to prevent clipping
            peak = np.max(np.abs(y_filtered))
            if peak > 0.95:
                y_filtered = y_filtered * (0.95 / peak)
            
            # Save output
            sf.write(output_path, y_filtered, sr)
            
            logger.info(f"EQ applied: {', '.join(filters_applied)}")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "filters_applied": filters_applied,
                "high_pass_freq": high_pass_freq,
                "low_pass_freq": low_pass_freq,
                "boost_freq": boost_freq,
                "boost_db": boost_db if boost_freq else 0
            }
            
        except Exception as e:
            logger.error(f"Error applying EQ: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
    async def remove_artifacts(
        self,
        file_path: str,
        sensitivity: float,
        output_path: str
    ) -> dict:
        """
        Detect and remove clicks, pops, and digital glitches.
        
        Args:
            file_path: Path to input audio file
            sensitivity: Detection sensitivity 0-1 (default: 0.5)
            output_path: Path for output file
            
        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            
            # Calculate first derivative to detect rapid changes
            derivative = np.diff(y, prepend=y[0])
            
            # Calculate threshold based on sensitivity
            threshold = np.percentile(np.abs(derivative), 100 - (sensitivity * 20))
            
            # Detect artifacts (rapid changes exceeding threshold)
            artifact_mask = np.abs(derivative) > threshold
            
            # Expand mask slightly to catch artifact tails
            kernel_size = int(sr * 0.001)  # 1ms kernel
            kernel = np.ones(kernel_size)
            artifact_mask_expanded = signal.convolve(
                artifact_mask.astype(float), 
                kernel, 
                mode='same'
            ) > 0
            
            # Count artifacts
            artifact_count = np.sum(np.diff(artifact_mask_expanded.astype(int)) > 0)
            
            # Interpolate over artifacts
            y_cleaned = y.copy()
            artifact_indices = np.where(artifact_mask_expanded)[0]
            
            if len(artifact_indices) > 0:
                # Group consecutive indices into regions
                regions = []
                start = artifact_indices[0]
                for i in range(1, len(artifact_indices)):
                    if artifact_indices[i] != artifact_indices[i-1] + 1:
                        regions.append((start, artifact_indices[i-1]))
                        start = artifact_indices[i]
                regions.append((start, artifact_indices[-1]))
                
                # Interpolate each region
                for start, end in regions:
                    if start > 0 and end < len(y_cleaned) - 1:
                        # Linear interpolation
                        y_cleaned[start:end+1] = np.linspace(
                            y_cleaned[start-1],
                            y_cleaned[end+1],
                            end - start + 1
                        )
            
            # Apply gentle smoothing
            window_size = int(sr * 0.0005)  # 0.5ms smoothing
            if window_size % 2 == 0:
                window_size += 1
            y_cleaned = signal.savgol_filter(y_cleaned, window_size, 3)
            
            # Save output
            sf.write(output_path, y_cleaned, sr)
            
            logger.info(f"Removed {artifact_count} artifacts")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "artifacts_removed": int(artifact_count),
                "sensitivity": sensitivity
            }
            
        except Exception as e:
            logger.error(f"Error removing artifacts: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }

    
    async def run(self):
        """Run the MCP server."""
        await self.initialize()
        
        async with stdio_server() as (read_stream, write_stream):
            await self.app.run(
                read_stream,
                write_stream,
                self.app.create_initialization_options()
            )


async def main():
    """Main entry point for the MCP server."""
    server = BigFlavorMCPServer(enable_audio_analysis=True)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
