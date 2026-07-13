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

# Mains-hum detection/removal (issue #57)
MAINS_FUNDAMENTALS_HZ = (50.0, 60.0)
HUM_MAX_FREQ_HZ = 500.0      # harmonics above this rarely carry audible hum
HUM_PROMINENCE_DB = 10.0     # narrow peak must stand this far above the local baseline
HUM_NOTCH_Q = 30.0           # notch bandwidth = freq / Q (~2 Hz at 60 Hz)

# Auto-clean chain precision (issue #58): the processing is float end-to-end,
# so intermediate step files are written as 32-bit float WAV — re-quantizing to
# soundfile's 16-bit default between steps adds noise at the very floor the
# chain is cleaning. Only the final output is quantized, once, to 24-bit PCM
# (the deliberate master bit depth).
INTERMEDIATE_WAV_SUBTYPE = "FLOAT"
FINAL_WAV_SUBTYPE = "PCM_24"


def _load_audio(file_path: str, sr: Optional[int] = None) -> tuple:
    """Load audio preserving the input's channel count.

    Returns (y, sample_rate) where y is 1-D for mono input or
    (channels, samples) for multi-channel input (librosa layout).
    """
    import librosa

    return librosa.load(file_path, sr=sr, mono=False)


def _to_mono(y):
    """Mono reference mix for analysis (beat/pitch/RMS detection)."""
    import librosa

    return librosa.to_mono(y) if y.ndim > 1 else y


def _apply_per_channel(y, process):
    """Apply a 1-D signal-processing function to each channel.

    Mono passes straight through. Multi-channel results are trimmed to the
    shortest channel because STFT round-trips can differ by a few samples.
    """
    import numpy as np

    if y.ndim == 1:
        return process(y)
    processed = [process(channel) for channel in y]
    min_len = min(p.shape[-1] for p in processed)
    return np.vstack([p[..., :min_len] for p in processed])


def _write_audio(output_path: str, y, sr: int, subtype: Optional[str] = None) -> None:
    """Write audio, converting librosa's (channels, samples) layout to
    soundfile's (samples, channels). `subtype` defaults to soundfile's own
    default (PCM_16) when not given; pass INTERMEDIATE_WAV_SUBTYPE /
    FINAL_WAV_SUBTYPE explicitly where precision matters (issue #58)."""
    import soundfile as sf

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)


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
                # INTELLIGENT AUTO-PROCESSING
                Tool(
                    name="analyze_and_recommend_processing",
                    description="Analyze audio and recommend optimal processing settings. Detects issues like noise, clipping, frequency imbalance, and suggests the best cleanup workflow with specific parameters.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to analyze"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                Tool(
                    name="auto_clean_recording",
                    description="Automatically analyze and clean a raw recording with intelligent parameter selection. Detects and removes leading/trailing noise (not just silence), applies optimal noise reduction, EQ, normalization, and mastering based on audio analysis.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the raw recording to clean"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for the cleaned file"
                            },
                            "aggressiveness": {
                                "type": "string",
                                "description": "Processing aggressiveness: 'gentle', 'moderate', or 'aggressive' (default: 'moderate')"
                            },
                            "keep_intermediates": {
                                "type": "boolean",
                                "description": "Save intermediate processing steps for review (default: false)"
                            }
                        },
                        "required": ["file_path", "output_path"]
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
                                "description": "Amount of the quietest audio (in seconds) used to estimate the noise profile (default: 1.0)"
                            },
                            "reduction_strength": {
                                "type": "number",
                                "description": "Noise reduction strength 0-1 (default: 0.7)"
                            },
                            "highpass_hz": {
                                "type": "number",
                                "description": "Optional high-pass cutoff in Hz to remove low-frequency rumble (default: off; use the EQ tool for rumble control)"
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
                    name="remove_hum",
                    description="Detect and remove mains electrical hum (50 or 60 Hz fundamental and its harmonics) using narrow high-Q notch filters that leave nearby musical content intact",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the audio file to de-hum"
                            },
                            "output_path": {
                                "type": "string",
                                "description": "Output path for the de-hummed file"
                            },
                            "fundamental_hz": {
                                "type": "number",
                                "description": "Mains fundamental to notch (50 or 60). Auto-detected when omitted."
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
                elif name == "analyze_and_recommend_processing":
                    result = await self.analyze_and_recommend_processing(arguments["file_path"])
                elif name == "auto_clean_recording":
                    result = await self.auto_clean_recording(
                        arguments["file_path"],
                        arguments["output_path"],
                        arguments.get("aggressiveness", "moderate"),
                        arguments.get("keep_intermediates", False)
                    )
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
                        arguments["output_path"],
                        arguments.get("highpass_hz")
                    )
                elif name == "remove_hum":
                    result = await self.remove_hum(
                        arguments["file_path"],
                        arguments["output_path"],
                        arguments.get("fundamental_hz")
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
            
            # Load audio (channel count preserved; analysis uses a mono mix)
            y, sr = _load_audio(file_path, sr=22050)

            # Detect current tempo
            tempo, _ = librosa.beat.beat_track(y=_to_mono(y), sr=sr)
            current_bpm = tempo if isinstance(tempo, float) else tempo[0]

            # Calculate stretch ratio
            stretch_ratio = target_bpm / current_bpm

            # Time-stretch audio
            y_stretched = _apply_per_channel(
                y, lambda ch: librosa.effects.time_stretch(ch, rate=stretch_ratio)
            )

            # Save output
            _write_audio(output_path, y_stretched, sr)
            
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
            
            # Load both songs (channel counts preserved)
            y1, sr1 = _load_audio(song1_path, sr=22050)
            y2, sr2 = _load_audio(song2_path, sr=22050)

            # Match channel counts: duplicate a mono song so a stereo partner
            # keeps its stereo image.
            if y1.ndim != y2.ndim:
                if y1.ndim == 1:
                    y1 = np.tile(y1, (y2.shape[0], 1))
                else:
                    y2 = np.tile(y2, (y1.shape[0], 1))

            # Resample if sample rates differ
            if sr1 != sr2:
                y2 = librosa.resample(y2, orig_sr=sr2, target_sr=sr1)
                sr = sr1
            else:
                sr = sr1

            # Detect tempos
            tempo1, beats1 = librosa.beat.beat_track(y=_to_mono(y1), sr=sr)
            tempo2, beats2 = librosa.beat.beat_track(y=_to_mono(y2), sr=sr)

            bpm1 = tempo1 if isinstance(tempo1, float) else tempo1[0]
            bpm2 = tempo2 if isinstance(tempo2, float) else tempo2[0]

            # Time-stretch song2 to match song1's tempo
            if abs(bpm1 - bpm2) > 1:
                stretch_ratio = bpm1 / bpm2
                y2 = _apply_per_channel(
                    y2, lambda ch: librosa.effects.time_stretch(ch, rate=stretch_ratio)
                )

            # Calculate transition length in samples
            transition_samples = int(transition_duration * sr)

            # Get ending of song1 and beginning of song2
            song1_end = y1[..., -transition_samples:]
            song2_start = y2[..., :transition_samples]

            # Create crossfade
            fade_out = np.linspace(1, 0, transition_samples)
            fade_in = np.linspace(0, 1, transition_samples)

            transition = song1_end * fade_out + song2_start * fade_in

            # Concatenate: song1 (minus transition) + transition + song2 (minus transition)
            output = np.concatenate([
                y1[..., :-transition_samples],
                transition,
                y2[..., transition_samples:]
            ], axis=-1)

            # Save output
            _write_audio(output_path, output, sr)
            
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

        WAV output is written as 24-bit PCM (``FINAL_WAV_SUBTYPE``) — a master
        is a final deliverable, so its bit depth is a deliberate choice rather
        than soundfile's 16-bit default.

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
            
            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)

            # Apply high-pass filter to remove rumble (sosfilt runs along the
            # last axis, so this handles mono and stereo alike)
            sos = signal.butter(4, 30, 'hp', fs=sr, output='sos')
            y_filtered = signal.sosfilt(sos, y)
            n_samples = y_filtered.shape[-1]

            # Apply smooth RMS-based mastering compression. The gain envelope
            # is computed from the mono mix and applied to all channels
            # (linked stereo) so the stereo balance is preserved.
            frame_length = int(sr * 0.05)  # 50ms window
            hop_length = int(sr * 0.01)    # 10ms hop

            rms = librosa.feature.rms(y=_to_mono(y_filtered), frame_length=frame_length, hop_length=hop_length)[0]

            # Upsample RMS to match audio length
            rms_full = np.interp(
                np.arange(n_samples),
                np.arange(len(rms)) * hop_length,
                rms
            )
            
            # Mastering compression parameters (more aggressive than mixing)
            threshold_db = -24.0
            ratio = 3.5
            knee_width = 6.0
            
            # Convert to dB
            rms_db = 20 * np.log10(rms_full + 1e-10)
            
            # Soft-knee compression curve
            def compress_db(level_db):
                if level_db < (threshold_db - knee_width / 2):
                    return level_db
                elif level_db > (threshold_db + knee_width / 2):
                    return threshold_db + (level_db - threshold_db) / ratio
                else:
                    # Smooth transition in knee region
                    x = level_db - threshold_db + knee_width / 2
                    return level_db + ((1 / ratio - 1) * (x ** 2)) / (2 * knee_width)
            
            compressed_db = np.array([compress_db(db) for db in rms_db])
            
            # Calculate gain reduction
            gain_reduction = librosa.db_to_amplitude(compressed_db - rms_db)
            
            # Apply attack/release smoothing
            attack_samples = int(sr * 0.003)   # 3ms attack (fast for mastering)
            release_samples = int(sr * 0.1)    # 100ms release (slow for smooth)
            
            smoothed_gain = np.copy(gain_reduction)
            for i in range(1, len(smoothed_gain)):
                if gain_reduction[i] < smoothed_gain[i - 1]:
                    # Attack (gaining down)
                    alpha = 1.0 - np.exp(-1.0 / attack_samples)
                else:
                    # Release (gaining up)
                    alpha = 1.0 - np.exp(-1.0 / release_samples)
                smoothed_gain[i] = alpha * gain_reduction[i] + (1 - alpha) * smoothed_gain[i - 1]
            
            # Apply compression
            y_compressed = y_filtered * smoothed_gain
            
            # Calculate current RMS level
            rms_current = np.sqrt(np.mean(y_compressed**2))
            
            # Target RMS based on LUFS (simplified conversion)
            # LUFS -14 ≈ RMS 0.25, LUFS -16 ≈ RMS 0.2
            target_rms = 10 ** ((target_loudness + 15) / 20)
            
            # Apply gain to reach target with safety margin
            if rms_current > 0:
                gain = target_rms / rms_current
                # Add safety headroom to prevent clipping
                max_gain = 0.9 / (np.max(np.abs(y_compressed)) + 1e-10)
                gain = min(gain, max_gain)
                y_gained = y_compressed * gain
            else:
                y_gained = y_compressed
                gain = 1.0
            
            # Apply smooth brick-wall limiter (prevents clipping completely)
            # Use lookahead for transparent limiting
            lookahead_ms = 5
            lookahead_samples = int(sr * lookahead_ms / 1000)
            
            # Create envelope of absolute values with lookahead. For stereo the
            # envelope tracks the loudest channel so one shared limiter gain
            # preserves the balance.
            abs_signal = np.max(np.abs(y_gained), axis=0) if y_gained.ndim > 1 else np.abs(y_gained)
            # Pad for lookahead
            abs_padded = np.pad(abs_signal, (0, lookahead_samples), mode='edge')

            # Find maximum in lookahead window
            from scipy.ndimage import maximum_filter
            envelope = maximum_filter(abs_padded, size=lookahead_samples)[:n_samples]
            
            # Calculate limiting gain (only reduce, never boost)
            limit_threshold = 0.95  # -0.5dB headroom
            limit_gain = np.where(envelope > limit_threshold, limit_threshold / (envelope + 1e-10), 1.0)
            
            # Smooth the gain reduction to avoid artifacts
            release_samples_limiter = int(sr * 0.05)  # 50ms release
            smoothed_limit_gain = np.copy(limit_gain)
            for i in range(1, len(smoothed_limit_gain)):
                if limit_gain[i] < smoothed_limit_gain[i - 1]:
                    # Instant attack for limiting
                    smoothed_limit_gain[i] = limit_gain[i]
                else:
                    # Smooth release
                    alpha = 1.0 - np.exp(-1.0 / release_samples_limiter)
                    smoothed_limit_gain[i] = alpha * limit_gain[i] + (1 - alpha) * smoothed_limit_gain[i - 1]
            
            # Apply limiter
            y_mastered = y_gained * smoothed_limit_gain

            # Save output at the deliberate master bit depth (WAV only —
            # other containers keep their format default subtype)
            master_subtype = FINAL_WAV_SUBTYPE if output_path.lower().endswith(".wav") else None
            _write_audio(output_path, y_mastered, sr, subtype=master_subtype)

            # Calculate final RMS
            final_rms = np.sqrt(np.mean(y_mastered**2))
            final_lufs = 20 * np.log10(final_rms) - 15
            
            logger.info(f"Mastering complete: {file_path} → {output_path}")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "target_loudness_lufs": float(target_loudness),
                "actual_loudness_lufs": round(float(final_lufs), 1),
                "gain_applied_db": round(float(20 * np.log10(gain)), 1) if gain > 0 else 0,
                "output_bit_depth": "24-bit PCM" if master_subtype else "format default"
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
    
    # ==================== INTELLIGENT AUTO-PROCESSING ====================
    
    async def analyze_and_recommend_processing(self, file_path: str) -> dict:
        """
        Analyze audio comprehensively and recommend optimal processing settings.
        
        Detects:
        - Leading/trailing noise and optimal trim points
        - Background noise levels and recommended reduction
        - Frequency imbalances and optimal EQ settings
        - Dynamic range and compression needs
        - Pitch/tuning issues
        - Overall loudness and mastering requirements
        
        Args:
            file_path: Path to audio file to analyze
            
        Returns:
            Comprehensive analysis with specific processing recommendations
        """
        try:
            import librosa
            import numpy as np
            from scipy import signal, stats
            
            logger.info(f"Performing comprehensive analysis on: {file_path}")
            
            # Load audio
            y, sr = librosa.load(file_path, sr=None)
            duration = len(y) / sr
            
            # ===== 1. ANALYZE LEADING/TRAILING CONTENT =====
            # Detect music vs noise/speech in beginning and end
            frame_length = int(sr * 0.1)  # 100ms frames
            hop_length = int(sr * 0.05)   # 50ms hops
            
            # Calculate energy envelope
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Calculate spectral features for music detection
            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=hop_length)[0]
            zcr = librosa.feature.zero_crossing_rate(y, frame_length=frame_length, hop_length=hop_length)[0]
            
            # Music typically has more consistent energy and spectral features
            # Calculate moving statistics to find where music starts/ends
            window_size = 20  # ~1 second windows
            rms_std = np.array([np.std(rms[max(0,i-window_size):i+window_size]) 
                               for i in range(len(rms))])
            
            # Find stable music regions (low variance in RMS = consistent music)
            music_threshold = np.percentile(rms_std, 30)
            is_music = rms_std < music_threshold
            is_music = is_music & (rms > np.percentile(rms, 10))  # Must also have energy
            
            # Find first and last music regions
            music_indices = np.where(is_music)[0]
            if len(music_indices) > 0:
                music_start_frame = music_indices[0]
                music_end_frame = music_indices[-1]
                
                # Convert to time
                trim_start_time = music_start_frame * hop_length / sr
                trim_end_time = (music_end_frame * hop_length / sr)
                
                # How much to trim
                trim_from_start = max(0, trim_start_time - 0.1)  # Keep 0.1s buffer
                trim_from_end = max(0, duration - trim_end_time - 0.1)
            else:
                trim_from_start = 0
                trim_from_end = 0
                trim_start_time = 0
                trim_end_time = duration
            
            # ===== 2. ANALYZE NOISE FLOOR =====
            # Sample quiet sections to estimate noise
            quiet_threshold = np.percentile(rms, 20)
            quiet_sections = rms < quiet_threshold
            quiet_samples = y[np.repeat(quiet_sections, hop_length)[:len(y)]]
            
            if len(quiet_samples) > sr:  # Need at least 1 second
                noise_level = np.sqrt(np.mean(quiet_samples**2))
                noise_level_db = 20 * np.log10(noise_level + 1e-10)
                
                # Recommend noise reduction strength based on noise level
                if noise_level_db > -40:
                    recommended_noise_reduction = 0.8
                elif noise_level_db > -50:
                    recommended_noise_reduction = 0.6
                else:
                    recommended_noise_reduction = 0.4
            else:
                noise_level_db = -60.0
                recommended_noise_reduction = 0.5

            # ===== 2b. DETECT MAINS HUM (issue #57) =====
            hum = self._detect_hum(y, sr)

            # ===== 3. ANALYZE FREQUENCY BALANCE =====
            # Get average spectrum
            D = np.abs(librosa.stft(y))
            avg_spectrum = np.mean(D, axis=1)
            freqs = librosa.fft_frequencies(sr=sr)
            
            # Analyze frequency bands
            bass_band = (freqs >= 20) & (freqs < 250)
            mid_band = (freqs >= 250) & (freqs < 2000)
            treble_band = (freqs >= 2000) & (freqs < 8000)
            
            bass_energy = np.mean(avg_spectrum[bass_band])
            mid_energy = np.mean(avg_spectrum[mid_band])
            treble_energy = np.mean(avg_spectrum[treble_band])
            
            total_energy = bass_energy + mid_energy + treble_energy
            bass_pct = 100 * bass_energy / total_energy
            mid_pct = 100 * mid_energy / total_energy
            treble_pct = 100 * treble_energy / total_energy
            
            # Recommend EQ adjustments
            eq_recommendations = []
            
            # Check for excessive low rumble
            sub_bass = (freqs >= 20) & (freqs < 60)
            sub_bass_energy = np.mean(avg_spectrum[sub_bass])
            if sub_bass_energy > bass_energy * 0.3:
                eq_recommendations.append({
                    "type": "high_pass",
                    "frequency": 80,
                    "reason": "Excessive low-frequency rumble detected"
                })
            elif sub_bass_energy > bass_energy * 0.2:
                eq_recommendations.append({
                    "type": "high_pass",
                    "frequency": 60,
                    "reason": "Some low-frequency rumble present"
                })
            
            # Check for muddy low-mids
            if bass_pct > 45:
                eq_recommendations.append({
                    "type": "reduce",
                    "frequency": 200,
                    "amount": -3,
                    "reason": "Bass-heavy mix, may sound muddy"
                })
            
            # Check for harsh highs or lack of clarity
            if treble_pct < 15:
                eq_recommendations.append({
                    "type": "boost",
                    "frequency": 4000,
                    "amount": 2,
                    "reason": "Lacks high-frequency clarity"
                })
            elif treble_pct > 35:
                eq_recommendations.append({
                    "type": "low_pass",
                    "frequency": 12000,
                    "reason": "Excessive high-frequency content (may be harsh)"
                })
            
            # ===== 4. ANALYZE DYNAMIC RANGE =====
            peak = np.max(np.abs(y))
            rms_overall = np.sqrt(np.mean(y**2))
            crest_factor = peak / (rms_overall + 1e-10)
            crest_factor_db = 20 * np.log10(crest_factor)
            
            # Check for clipping
            clipping_threshold = 0.99
            clipped_samples = np.sum(np.abs(y) > clipping_threshold)
            clipping_pct = 100 * clipped_samples / len(y)
            
            # Recommend compression based on dynamic range
            if crest_factor_db > 18:
                recommended_compression = "aggressive"
                compression_ratio = 4.0
            elif crest_factor_db > 14:
                recommended_compression = "moderate"
                compression_ratio = 3.0
            else:
                recommended_compression = "gentle"
                compression_ratio = 2.0
            
            # ===== 5. ANALYZE LOUDNESS =====
            peak_db = 20 * np.log10(peak) if peak > 0 else -np.inf
            rms_db = 20 * np.log10(rms_overall) if rms_overall > 0 else -np.inf
            
            # Estimate LUFS (simplified)
            estimated_lufs = rms_db - 15
            
            # Recommend mastering target
            if estimated_lufs < -30:
                recommended_lufs = -14
                recommended_gain = estimated_lufs + 14
            elif estimated_lufs < -20:
                recommended_lufs = -14
                recommended_gain = estimated_lufs + 14
            else:
                recommended_lufs = -14
                recommended_gain = min(estimated_lufs + 14, 12)  # Cap gain
            
            # ===== COMPILE RECOMMENDATIONS =====
            recommendations = {
                "trim": {
                    "recommended": bool(trim_from_start > 0.5 or trim_from_end > 0.5),
                    "trim_start_seconds": round(float(trim_from_start), 2),
                    "trim_end_seconds": round(float(trim_from_end), 2),
                    "detected_music_start": round(float(trim_start_time), 2),
                    "detected_music_end": round(float(trim_end_time), 2),
                    "reason": "Non-musical content detected before/after main audio"
                },
                "noise_reduction": {
                    "recommended": bool(noise_level_db > -55),
                    "noise_level_db": round(float(noise_level_db), 1),
                    "recommended_strength": float(recommended_noise_reduction),
                    "recommended_profile_duration": 1.0,
                    "reason": f"Background noise at {noise_level_db:.1f} dB"
                },
                "hum": {
                    "recommended": hum["detected"],
                    "fundamental_hz": hum["fundamental_hz"],
                    "harmonics_affected": hum["harmonics_affected"],
                    "prominence_db": hum["prominence_db"],
                    "reason": (
                        f"Mains hum detected at {hum['fundamental_hz']:.0f} Hz "
                        f"({len(hum['harmonics_affected'])} affected frequencies)"
                        if hum["detected"] else "No mains hum detected"
                    )
                },
                "eq": {
                    "recommended": len(eq_recommendations) > 0,
                    "adjustments": eq_recommendations,
                    "frequency_balance": {
                        "bass_percent": round(float(bass_pct), 1),
                        "mid_percent": round(float(mid_pct), 1),
                        "treble_percent": round(float(treble_pct), 1)
                    }
                },
                "compression": {
                    "recommended": True,
                    "level": recommended_compression,
                    "ratio": float(compression_ratio),
                    "crest_factor_db": round(float(crest_factor_db), 1),
                    "reason": f"Dynamic range: {crest_factor_db:.1f} dB"
                },
                "normalization": {
                    "recommended": bool(peak_db < -6 or peak_db > -1),
                    "current_peak_db": round(float(peak_db), 1),
                    "target_peak_db": -3.0,
                    "reason": "Level optimization needed"
                },
                "mastering": {
                    "recommended": True,
                    "current_lufs_estimate": round(float(estimated_lufs), 1),
                    "target_lufs": float(recommended_lufs),
                    "estimated_gain_db": round(float(recommended_gain), 1)
                },
                "warnings": []
            }
            
            # Add warnings
            if clipping_pct > 0.1:
                recommendations["warnings"].append(
                    f"Clipping detected: {clipping_pct:.2f}% of samples are clipped"
                )
            
            if estimated_lufs > -10:
                recommendations["warnings"].append(
                    "Audio is very loud and may be over-compressed"
                )
            
            logger.info(f"Analysis complete. {len(recommendations)} categories analyzed")
            
            return {
                "status": "success",
                "file_path": file_path,
                "duration_seconds": round(float(duration), 2),
                "sample_rate": int(sr),
                "recommendations": recommendations,
                "processing_order": [
                    "1. Trim non-musical content" if recommendations["trim"]["recommended"] else None,
                    "2. Remove mains hum" if recommendations["hum"]["recommended"] else None,
                    "3. Reduce noise" if recommendations["noise_reduction"]["recommended"] else None,
                    "4. Apply EQ corrections" if recommendations["eq"]["recommended"] else None,
                    "5. Normalize with compression",
                    "6. Apply mastering"
                ],
                "summary": self._generate_analysis_summary(recommendations)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing audio: {e}")
            return {
                "status": "error",
                "error": str(e),
                "file_path": file_path
            }
    
    def _generate_analysis_summary(self, recommendations: dict) -> str:
        """Generate human-readable summary of analysis."""
        issues = []
        
        if recommendations["trim"]["recommended"]:
            trim_start = recommendations["trim"]["trim_start_seconds"]
            trim_end = recommendations["trim"]["trim_end_seconds"]
            issues.append(f"Found {trim_start:.1f}s of noise/speech at start, {trim_end:.1f}s at end")
        
        if recommendations["noise_reduction"]["recommended"]:
            noise_db = recommendations["noise_reduction"]["noise_level_db"]
            issues.append(f"Background noise at {noise_db:.1f} dB")

        if recommendations["hum"]["recommended"]:
            fundamental = recommendations["hum"]["fundamental_hz"]
            harmonic_count = len(recommendations["hum"]["harmonics_affected"])
            issues.append(
                f"Mains hum at {fundamental:.0f} Hz ({harmonic_count} affected frequencies)"
            )
        
        if recommendations["eq"]["recommended"]:
            issues.append(f"{len(recommendations['eq']['adjustments'])} frequency imbalances detected")
        
        if recommendations["warnings"]:
            issues.extend(recommendations["warnings"])
        
        if not issues:
            return "Audio is in good condition, only standard mastering recommended"
        
        return "; ".join(issues)
    
    async def auto_clean_recording(
        self,
        file_path: str,
        output_path: str,
        aggressiveness: str = "moderate",
        keep_intermediates: bool = False,
        steps_override: dict = None
    ) -> dict:
        """
        Automatically analyze and clean a raw recording with intelligent settings.

        Precision: intermediate step files are 32-bit float WAV (no
        re-quantization between steps); the final output is written once at
        24-bit PCM, reported as ``output_bit_depth`` in the result.

        Args:
            file_path: Path to raw recording
            output_path: Path for final cleaned output
            aggressiveness: 'gentle', 'moderate', or 'aggressive'
            keep_intermediates: Save intermediate processing steps
            steps_override: Optional per-step on/off map keyed by
                'trim', 'noise_reduction', 'eq', 'normalize', 'master'. A value
                forces that step on (True) or off (False), overriding the
                analysis recommendation; unspecified steps follow the analysis.

        Returns:
            Processing results with steps taken
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from pathlib import Path
            from scipy import signal

            logger.info(f"Auto-cleaning recording: {file_path} (aggressiveness: {aggressiveness})")

            # Step 1: Analyze to get recommendations
            analysis = await self.analyze_and_recommend_processing(file_path)

            if analysis.get("status") != "success":
                return analysis

            recommendations = analysis["recommendations"]

            # Apply caller step toggles on top of the recommendations. trim /
            # hum / noise_reduction / eq are gated by their "recommended" flag
            # below, so flip that flag; normalize / master always run unless
            # turned off.
            overrides = steps_override or {}
            for _step in ("trim", "hum", "noise_reduction", "eq"):
                if _step in overrides:
                    recommendations[_step]["recommended"] = bool(overrides[_step])
            do_normalize = bool(overrides.get("normalize", True))
            do_master = bool(overrides.get("master", True))

            # Adjust recommendations based on aggressiveness
            aggressiveness_multipliers = {
                "gentle": 0.7,
                "moderate": 1.0,
                "aggressive": 1.3
            }
            mult = aggressiveness_multipliers.get(aggressiveness, 1.0)
            
            # Track processing steps
            steps_taken = []
            current_file = file_path
            intermediate_dir = None
            
            if keep_intermediates:
                intermediate_dir = Path(output_path).parent / f"{Path(output_path).stem}_steps"
                intermediate_dir.mkdir(exist_ok=True)
            
            # Step 2: Intelligent trimming (not just silence - detect music vs noise/speech)
            if recommendations["trim"]["recommended"]:
                logger.info("Step 1: Intelligent trimming...")
                
                # Load audio (channel count preserved)
                y, sr = _load_audio(current_file)

                # Calculate trim points from analysis
                trim_start_samples = int(recommendations["trim"]["detected_music_start"] * sr)
                detected_end = recommendations["trim"]["detected_music_end"]
                trim_end_samples = int(detected_end * sr)

                # Add small buffer
                buffer_samples = int(0.1 * sr)
                trim_start = max(0, trim_start_samples - buffer_samples)
                trim_end = min(y.shape[-1], trim_end_samples + buffer_samples)

                # Trim
                y_trimmed = y[..., trim_start:trim_end]

                # Save
                if keep_intermediates:
                    trim_output = intermediate_dir / "01_trimmed.wav"
                else:
                    import tempfile
                    trim_output = Path(tempfile.mktemp(suffix=".wav"))

                _write_audio(str(trim_output), y_trimmed, sr, subtype=INTERMEDIATE_WAV_SUBTYPE)
                current_file = str(trim_output)

                steps_taken.append({
                    "step": "trim",
                    "trimmed_start_seconds": round(trim_start / sr, 2),
                    "trimmed_end_seconds": round((y.shape[-1] - trim_end) / sr, 2),
                    "output": str(trim_output) if keep_intermediates else "temp"
                })

            # Step 2b: Mains-hum removal — before broadband noise reduction so
            # the narrow notches handle hum the spectral gate can't (issue #57).
            if recommendations["hum"]["recommended"]:
                logger.info("Step 1b: Hum removal...")

                if keep_intermediates:
                    hum_output = intermediate_dir / "01b_dehummed.wav"
                else:
                    import tempfile
                    hum_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await self.remove_hum(
                    current_file,
                    str(hum_output),
                    fundamental_hz=recommendations["hum"]["fundamental_hz"]
                )

                if result.get("status") == "success" and result.get("hum_detected"):
                    current_file = str(hum_output)
                    steps_taken.append({
                        "step": "hum_removal",
                        "fundamental_hz": result.get("fundamental_hz"),
                        "harmonics_notched": result.get("harmonics_notched"),
                        "output": str(hum_output) if keep_intermediates else "temp"
                    })

            # Step 3: Noise reduction
            if recommendations["noise_reduction"]["recommended"]:
                logger.info("Step 2: Noise reduction...")
                
                strength = recommendations["noise_reduction"]["recommended_strength"] * mult
                strength = min(1.0, strength)
                
                if keep_intermediates:
                    noise_output = intermediate_dir / "02_denoised.wav"
                else:
                    import tempfile
                    noise_output = Path(tempfile.mktemp(suffix=".wav"))
                
                result = await self.reduce_noise(
                    current_file,
                    recommendations["noise_reduction"]["recommended_profile_duration"],
                    strength,
                    str(noise_output),
                    subtype=INTERMEDIATE_WAV_SUBTYPE
                )
                
                if result.get("status") == "success":
                    current_file = str(noise_output)
                    steps_taken.append({
                        "step": "noise_reduction",
                        "strength": round(strength, 2),
                        "reduction_db": result.get("noise_reduction_db"),
                        "output": str(noise_output) if keep_intermediates else "temp"
                    })
            
            # Step 4: Apply EQ corrections
            if recommendations["eq"]["recommended"]:
                logger.info("Step 3: Applying EQ...")
                
                eq_adjustments = recommendations["eq"]["adjustments"]
                
                # Apply recommended EQ
                high_pass_freq = None
                low_pass_freq = None
                boost_freq = None
                boost_db = None
                
                for adj in eq_adjustments:
                    if adj["type"] == "high_pass":
                        high_pass_freq = adj["frequency"]
                    elif adj["type"] == "low_pass":
                        low_pass_freq = adj["frequency"]
                    elif adj["type"] == "boost":
                        boost_freq = adj["frequency"]
                        boost_db = adj["amount"] * mult
                    elif adj["type"] == "reduce":
                        # Treat reduce as negative boost
                        boost_freq = adj["frequency"]
                        boost_db = adj["amount"] * mult
                
                if keep_intermediates:
                    eq_output = intermediate_dir / "03_eq.wav"
                else:
                    import tempfile
                    eq_output = Path(tempfile.mktemp(suffix=".wav"))
                
                result = await self.apply_eq(
                    current_file,
                    high_pass_freq or 30,
                    low_pass_freq,
                    boost_freq,
                    boost_db or 0,
                    str(eq_output),
                    subtype=INTERMEDIATE_WAV_SUBTYPE
                )
                
                if result.get("status") == "success":
                    current_file = str(eq_output)
                    steps_taken.append({
                        "step": "eq",
                        "adjustments": eq_adjustments,
                        "output": str(eq_output) if keep_intermediates else "temp"
                    })
            
            # Step 5: Normalize with compression
            if do_normalize:
                logger.info("Step 4: Normalization...")

                comp_ratio = recommendations["compression"]["ratio"]
                if aggressiveness == "aggressive":
                    comp_ratio *= 1.2
                elif aggressiveness == "gentle":
                    comp_ratio *= 0.8

                if keep_intermediates:
                    norm_output = intermediate_dir / "04_normalized.wav"
                else:
                    import tempfile
                    norm_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await self.normalize_audio(
                    current_file,
                    -3.0,
                    True,
                    str(norm_output),
                    subtype=INTERMEDIATE_WAV_SUBTYPE
                )

                if result.get("status") == "success":
                    current_file = str(norm_output)
                    steps_taken.append({
                        "step": "normalize",
                        "target_peak_db": -3.0,
                        "gain_applied_db": result.get("gain_applied_db"),
                        "output": str(norm_output) if keep_intermediates else "temp"
                    })

            # Step 6: Final mastering. Mastering normally writes output_path; if
            # the caller disabled it, write the current intermediate there so the
            # cleaned result still lands at output_path.
            if do_master:
                logger.info("Step 5: Mastering...")

                target_lufs = recommendations["mastering"]["target_lufs"]

                result = await self.apply_mastering(
                    current_file,
                    target_lufs,
                    output_path
                )

                if result.get("status") == "success":
                    steps_taken.append({
                        "step": "mastering",
                        "target_lufs": target_lufs,
                        "actual_lufs": result.get("actual_loudness_lufs"),
                        "gain_applied_db": result.get("gain_applied_db"),
                        "output": output_path
                    })
            else:
                # No mastering: still write the final once at the deliberate
                # bit depth (the last intermediate is float WAV, not a
                # deliverable format). Channel count preserved (issue #55).
                y_final, sr_final = _load_audio(current_file)
                final_subtype = FINAL_WAV_SUBTYPE if output_path.lower().endswith(".wav") else None
                _write_audio(output_path, y_final, sr_final, subtype=final_subtype)

            # Clean up temp files if not keeping intermediates
            if not keep_intermediates:
                for step in steps_taken:
                    if step.get("output") and step["output"] != "temp" and step["output"] != output_path:
                        try:
                            Path(step["output"]).unlink()
                        except:
                            pass
            
            logger.info(f"Auto-cleaning complete: {len(steps_taken)} steps applied")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "aggressiveness": aggressiveness,
                "analysis_summary": analysis.get("summary"),
                "steps_applied": steps_taken,
                "intermediate_files": str(intermediate_dir) if keep_intermediates else None,
                "output_bit_depth": "24-bit PCM" if output_path.lower().endswith(".wav") else "format default",
                "total_steps": len(steps_taken),
                "recommendations_followed": {
                    "trim": any(s["step"] == "trim" for s in steps_taken),
                    "hum_removal": any(s["step"] == "hum_removal" for s in steps_taken),
                    "noise_reduction": any(s["step"] == "noise_reduction" for s in steps_taken),
                    "eq": any(s["step"] == "eq" for s in steps_taken),
                    "normalize": any(s["step"] == "normalize" for s in steps_taken),
                    "mastering": any(s["step"] == "mastering" for s in steps_taken)
                }
            }
            
        except Exception as e:
            logger.error(f"Error auto-cleaning recording: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
    
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
            
            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)
            original_duration = y.shape[-1] / sr

            # Convert threshold from dB to amplitude
            threshold_amplitude = librosa.db_to_amplitude(threshold_db)

            # Find non-silent intervals on the mono mix so both channels share
            # the same trim points
            non_silent = librosa.effects.split(_to_mono(y), top_db=-threshold_db)

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
            y_trimmed = y[..., start_sample:end_sample]
            trimmed_duration = y_trimmed.shape[-1] / sr

            # Save output
            _write_audio(output_path, y_trimmed, sr)
            
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
        output_path: str,
        highpass_hz: Optional[float] = None,
        subtype: Optional[str] = None
    ) -> dict:
        """
        Remove background noise, hum, hiss, and feedback.
        Uses spectral gating with a smoothed time-frequency mask.

        Args:
            file_path: Path to input audio file
            noise_profile_duration: Amount of the quietest audio (in seconds)
                used to estimate the noise profile (default: 1.0)
            reduction_strength: Reduction strength 0-1 (default: 0.7)
            output_path: Path for output file
            highpass_hz: Optional high-pass cutoff in Hz for rumble removal.
                Off by default — rumble control belongs to the EQ step.
            subtype: Optional soundfile subtype for the output (e.g. 'FLOAT'
                for lossless chain intermediates); None keeps the format default

        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            from scipy.ndimage import median_filter

            # Load audio (channel count preserved; each channel is denoised
            # independently with its own noise profile)
            y, sr = _load_audio(file_path)
            hop_length = 512  # librosa.stft default
            channel_stats = []  # (original_noise, reduced_noise) per channel

            def denoise_channel(ch: np.ndarray) -> np.ndarray:
                n_samples = ch.shape[-1]

                # Compute STFT
                D = librosa.stft(ch)
                mag = np.abs(D)
                phase = np.angle(D)

                # Estimate the noise spectrum from the quietest frames of the
                # whole channel rather than its opening seconds: in the
                # auto-clean chain the input is already trimmed to music
                # start, so "the beginning" is music, not noise (issue #56).
                frame_rms = np.sqrt((mag ** 2).mean(axis=0))
                n_noise_frames = int(round(noise_profile_duration * sr / hop_length))
                n_noise_frames = max(1, min(n_noise_frames, mag.shape[1]))
                quietest_frames = np.argsort(frame_rms)[:n_noise_frames]
                noise_mag = mag[:, quietest_frames].mean(axis=1, keepdims=True)

                # Spectral gating: reduce magnitude where it's close to noise level
                # Scale noise threshold by reduction strength
                noise_threshold = noise_mag * (2 - reduction_strength)

                # Apply soft gating, then smooth the mask across frequency and
                # time so isolated bins don't flip open/closed frame-to-frame
                # (the source of watery "musical noise" artifacts).
                mask = np.maximum(0, 1 - (noise_threshold / (mag + 1e-10)))
                mask = median_filter(mask, size=(3, 5))
                mag_reduced = mag * mask

                # Reconstruct signal at the original channel length
                D_reduced = mag_reduced * np.exp(1j * phase)
                ch_denoised = librosa.istft(D_reduced, length=n_samples)

                if highpass_hz:
                    sos = signal.butter(4, highpass_hz, 'hp', fs=sr, output='sos')
                    ch_denoised = signal.sosfilt(sos, ch_denoised)

                # Noise floor before vs after, measured on the quietest frames
                rms_after = np.sqrt((np.abs(librosa.stft(ch_denoised)) ** 2).mean(axis=0))
                channel_stats.append((
                    float(frame_rms[quietest_frames].mean()),
                    float(rms_after[quietest_frames].mean())
                ))

                return ch_denoised

            y_filtered = _apply_per_channel(y, denoise_channel)

            # Save output
            _write_audio(output_path, y_filtered, sr, subtype=subtype)

            original_noise = float(np.mean([s[0] for s in channel_stats]))
            reduced_noise = float(np.mean([s[1] for s in channel_stats]))
            noise_reduction_db = 20 * np.log10(original_noise / (reduced_noise + 1e-10))

            logger.info(f"Noise reduction applied: {noise_reduction_db:.1f} dB reduction")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "reduction_strength": reduction_strength,
                "noise_reduction_db": round(float(noise_reduction_db), 1),
                "noise_profile_duration": noise_profile_duration,
                "highpass_hz": highpass_hz
            }
            
        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }

    def _detect_hum(self, y, sr) -> dict:
        """
        Detect mains hum: persistent narrow spectral peaks at a 50 or 60 Hz
        fundamental and its harmonics (issue #57).

        Uses the median magnitude spectrum over time so persistent components
        (hum) survive while transient musical content is suppressed. A
        fundamental counts as detected when its own peak is prominent or at
        least two of its harmonics are (hum sometimes has a weak fundamental
        but strong harmonics).

        Returns:
            {"detected": bool, "fundamental_hz": float | None,
             "harmonics_affected": [float], "prominence_db": {freq: dB}}
        """
        import librosa
        import numpy as np

        n_fft = 16384
        while n_fft > len(y) and n_fft > 2048:
            n_fft //= 2
        spectrum = np.median(np.abs(librosa.stft(y, n_fft=n_fft)), axis=1)
        freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

        def peak_prominence_db(freq: float) -> float:
            offset = np.abs(freqs - freq)
            band = offset <= 3.0
            baseline_band = (offset > 6.0) & (offset <= 30.0)
            if not band.any() or not baseline_band.any():
                return 0.0
            peak = spectrum[band].max()
            baseline = np.median(spectrum[baseline_band])
            return float(20 * np.log10((peak + 1e-10) / (baseline + 1e-10)))

        best = {
            "detected": False,
            "fundamental_hz": None,
            "harmonics_affected": [],
            "prominence_db": {}
        }
        best_score = 0.0
        for f0 in MAINS_FUNDAMENTALS_HZ:
            affected = []
            prominences = {}
            harmonic = f0
            while harmonic <= min(HUM_MAX_FREQ_HZ, sr / 2 - 30.0):
                prominence = peak_prominence_db(harmonic)
                if prominence >= HUM_PROMINENCE_DB:
                    affected.append(harmonic)
                    prominences[harmonic] = round(prominence, 1)
                harmonic += f0
            detected = f0 in affected or len(affected) >= 2
            score = sum(prominences.values())
            if detected and score > best_score:
                best = {
                    "detected": True,
                    "fundamental_hz": f0,
                    "harmonics_affected": affected,
                    "prominence_db": prominences
                }
                best_score = score
        return best

    async def remove_hum(
        self,
        file_path: str,
        output_path: str,
        fundamental_hz: Optional[float] = None
    ) -> dict:
        """
        Remove mains hum with narrow high-Q notch filters at the fundamental
        and its affected harmonics, leaving nearby content intact (issue #57).

        Args:
            file_path: Path to input audio file
            output_path: Path for output file
            fundamental_hz: Mains fundamental to notch (50 or 60).
                Auto-detected when omitted; when no hum is found the audio is
                copied unchanged.

        Returns:
            Operation result
        """
        try:
            import shutil

            import librosa
            import numpy as np
            import soundfile as sf
            from scipy import signal

            y, sr = librosa.load(file_path, sr=None)
            detection = self._detect_hum(y, sr)

            if fundamental_hz is not None:
                fundamental_hz = float(fundamental_hz)
                if detection["detected"] and detection["fundamental_hz"] == fundamental_hz:
                    notch_freqs = detection["harmonics_affected"]
                else:
                    # Forced fundamental without a matching detection: notch
                    # the fundamental and its first few harmonics.
                    notch_freqs = [fundamental_hz * k for k in range(1, 5)]
            elif detection["detected"]:
                fundamental_hz = detection["fundamental_hz"]
                notch_freqs = detection["harmonics_affected"]
            else:
                shutil.copyfile(file_path, output_path)
                logger.info(f"No mains hum detected in {file_path}; copied unchanged")
                return {
                    "status": "success",
                    "hum_detected": False,
                    "input_file": file_path,
                    "output_file": output_path,
                    "message": "No mains hum detected; audio copied unchanged"
                }

            notch_freqs = [float(f) for f in notch_freqs if f < sr / 2 * 0.9]
            y_filtered = y
            for freq in notch_freqs:
                b, a = signal.iirnotch(freq, HUM_NOTCH_Q, fs=sr)
                # Zero-phase filtering: no phase distortion, double attenuation
                y_filtered = signal.filtfilt(b, a, y_filtered)

            sf.write(output_path, y_filtered.astype(np.float32), sr)

            residual = self._detect_hum(y_filtered, sr)
            logger.info(
                f"Hum removal: notched {len(notch_freqs)} frequencies "
                f"(fundamental {fundamental_hz:.0f} Hz)"
            )

            return {
                "status": "success",
                "hum_detected": True,
                "fundamental_hz": fundamental_hz,
                "harmonics_notched": notch_freqs,
                "prominence_db": detection["prominence_db"],
                "residual_hum_detected": residual["detected"],
                "input_file": file_path,
                "output_file": output_path
            }

        except Exception as e:
            logger.error(f"Error removing hum: {e}")
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
            
            # Load audio (channel count preserved; pitch detection on mono mix)
            y, sr = _load_audio(file_path)

            if auto_tune:
                # Extract pitch using piptrack
                pitches, magnitudes = librosa.piptrack(y=_to_mono(y), sr=sr)
                
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
                y_corrected = _apply_per_channel(
                    y,
                    lambda ch: librosa.effects.pitch_shift(ch, sr=sr, n_steps=correction_semitones)
                )
            else:
                y_corrected = y
                logger.info("No pitch correction needed")

            # Save output
            _write_audio(output_path, y_corrected, sr)
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "semitones_shift": round(float(correction_semitones), 2),
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
        output_path: str,
        subtype: Optional[str] = None
    ) -> dict:
        """
        Normalize audio levels and optionally apply compression.

        Args:
            file_path: Path to input audio file
            target_level_db: Target peak level in dB (default: -3)
            apply_compression: Apply dynamic range compression
            output_path: Path for output file
            subtype: Optional soundfile subtype for the output (e.g. 'FLOAT'
                for lossless chain intermediates); None keeps the format default

        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            
            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)
            n_samples = y.shape[-1]

            # Calculate current peak level
            current_peak = np.max(np.abs(y))
            current_peak_db = 20 * np.log10(current_peak) if current_peak > 0 else -np.inf

            if apply_compression:
                # Apply smooth RMS-based compression to avoid clicks. The gain
                # envelope comes from the mono mix and is shared by all
                # channels (linked stereo) so the balance is preserved.
                from scipy import signal

                # Calculate RMS envelope with longer window for smoother compression
                frame_length = int(sr * 0.05)  # 50ms window
                hop_length = int(sr * 0.01)    # 10ms hop

                rms = librosa.feature.rms(y=_to_mono(y), frame_length=frame_length, hop_length=hop_length)[0]

                # Upsample RMS to match audio length
                rms_full = np.interp(
                    np.arange(n_samples),
                    np.arange(len(rms)) * hop_length,
                    rms
                )
                
                # Gentle compression parameters
                threshold_db = -20.0
                ratio = 2.5
                knee_width = 10.0
                
                # Convert to dB
                rms_db = 20 * np.log10(rms_full + 1e-10)
                
                # Soft-knee compression curve
                def compress_db(level_db):
                    if level_db < (threshold_db - knee_width / 2):
                        return level_db
                    elif level_db > (threshold_db + knee_width / 2):
                        return threshold_db + (level_db - threshold_db) / ratio
                    else:
                        # Smooth transition in knee region
                        x = level_db - threshold_db + knee_width / 2
                        return level_db + ((1 / ratio - 1) * (x ** 2)) / (2 * knee_width)
                
                compressed_db = np.array([compress_db(db) for db in rms_db])
                
                # Calculate gain reduction in linear scale
                gain_reduction = librosa.db_to_amplitude(compressed_db - rms_db)
                
                # Apply attack/release smoothing to prevent clicks
                attack_samples = int(sr * 0.005)   # 5ms attack
                release_samples = int(sr * 0.05)   # 50ms release
                
                smoothed_gain = np.copy(gain_reduction)
                for i in range(1, len(smoothed_gain)):
                    if gain_reduction[i] < smoothed_gain[i - 1]:
                        # Attack (gaining down)
                        alpha = 1.0 - np.exp(-1.0 / attack_samples)
                    else:
                        # Release (gaining up)
                        alpha = 1.0 - np.exp(-1.0 / release_samples)
                    smoothed_gain[i] = alpha * gain_reduction[i] + (1 - alpha) * smoothed_gain[i - 1]
                
                # Apply compression
                y_compressed = y * smoothed_gain
            else:
                y_compressed = y
            
            # Normalize to target level with headroom to prevent clipping
            target_amplitude = librosa.db_to_amplitude(target_level_db)
            peak_after_compression = np.max(np.abs(y_compressed))
            
            if peak_after_compression > 0:
                # Add 0.5dB safety headroom
                safety_factor = 0.94  # ~-0.5dB
                gain = (target_amplitude / peak_after_compression) * safety_factor
                y_normalized = y_compressed * gain
            else:
                y_normalized = y_compressed
            
            # Soft clip if needed (should rarely happen now)
            def soft_clip(x):
                # Smooth saturation curve instead of hard clip
                return np.tanh(x * 0.9) / np.tanh(0.9)
            
            if np.max(np.abs(y_normalized)) > 0.99:
                y_normalized = soft_clip(y_normalized)

            # Save output
            _write_audio(output_path, y_normalized, sr, subtype=subtype)

            final_peak_db = 20 * np.log10(np.max(np.abs(y_normalized)))
            gain_applied_db = final_peak_db - current_peak_db
            
            logger.info(f"Normalized: {current_peak_db:.1f}dB → {final_peak_db:.1f}dB")
            
            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_peak_db": round(float(current_peak_db), 1),
                "target_peak_db": float(target_level_db),
                "final_peak_db": round(float(final_peak_db), 1),
                "gain_applied_db": round(float(gain_applied_db), 1),
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
        output_path: str,
        subtype: Optional[str] = None
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
            subtype: Optional soundfile subtype for the output (e.g. 'FLOAT'
                for lossless chain intermediates); None keeps the format default

        Returns:
            Operation result
        """
        try:
            import librosa
            import soundfile as sf
            import numpy as np
            from scipy import signal
            
            # Load audio (channel count preserved; sosfilt runs along the last
            # axis, so every filter below handles mono and stereo alike)
            y, sr = _load_audio(file_path)
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
            _write_audio(output_path, y_filtered, sr, subtype=subtype)

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
            
            # Load audio (channel count preserved; each channel is cleaned
            # independently)
            y, sr = _load_audio(file_path)

            kernel_size = int(sr * 0.001)  # 1ms kernel
            kernel = np.ones(kernel_size)
            window_size = int(sr * 0.0005)  # 0.5ms smoothing
            if window_size % 2 == 0:
                window_size += 1

            artifact_count = 0

            def clean_channel(ch: np.ndarray) -> np.ndarray:
                nonlocal artifact_count

                # Calculate first derivative to detect rapid changes
                derivative = np.diff(ch, prepend=ch[0])

                # Calculate threshold based on sensitivity
                threshold = np.percentile(np.abs(derivative), 100 - (sensitivity * 20))

                # Detect artifacts (rapid changes exceeding threshold)
                artifact_mask = np.abs(derivative) > threshold

                # Expand mask slightly to catch artifact tails
                artifact_mask_expanded = signal.convolve(
                    artifact_mask.astype(float),
                    kernel,
                    mode='same'
                ) > 0

                # Count artifacts
                artifact_count += int(np.sum(np.diff(artifact_mask_expanded.astype(int)) > 0))

                # Interpolate over artifacts
                ch_cleaned = ch.copy()
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
                        if start > 0 and end < len(ch_cleaned) - 1:
                            # Linear interpolation
                            ch_cleaned[start:end+1] = np.linspace(
                                ch_cleaned[start-1],
                                ch_cleaned[end+1],
                                end - start + 1
                            )

                # Apply gentle smoothing
                return signal.savgol_filter(ch_cleaned, window_size, 3)

            y_cleaned = _apply_per_channel(y, clean_channel)

            # Save output
            _write_audio(output_path, y_cleaned, sr)

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
