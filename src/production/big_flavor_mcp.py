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
