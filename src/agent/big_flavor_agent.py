"""
Big Flavor Band Agent with Claude + RAG + MCP Integration
Uses Claude with:
- RAG System (library) for search/read operations
- Production MCP Server for write/modify operations
Architecture:
- RAG System: Python library for search and retrieval
- MCP Server: Separate service for production/modification
"""

import asyncio
import json
import logging
import os
from typing import Optional, List, Dict, Any
from pathlib import Path

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("big-flavor-agent")


class BigFlavorAgent:
    """
    Big Flavor Band AI Agent powered by Claude.
    Integrates:
    - RAG system library for search (direct access)
    - Production MCP server for audio processing
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Claude agent with RAG system and MCP server.
        
        Args:
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-haiku-20240307"
        self.conversation_history = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        
        # Import RAG system library and production server
        import sys
        from pathlib import Path
        
        # Add parent directories to path for imports
        project_root = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(project_root))
        sys.path.insert(0, str(project_root / "src" / "rag"))
        sys.path.insert(0, str(project_root / "src" / "production"))
        sys.path.insert(0, str(project_root / "database"))
        
        from big_flavor_rag import SongRAGSystem
        from database import DatabaseManager
        from big_flavor_mcp import BigFlavorMCPServer
        
        # Direct access to RAG system library
        self.db_manager = DatabaseManager()
        self.rag_system = None  # Will be initialized in initialize()
        
        # Production server for audio processing
        self.production_server = BigFlavorMCPServer(enable_audio_analysis=True)
        
        logger.info(f"Claude RAG+MCP Agent initialized with model: {self.model}")
    
    async def initialize(self):
        """Initialize RAG system and production server."""
        logger.info("Initializing RAG system and Production server...")
        
        # Initialize database and RAG system
        await self.db_manager.connect()
        from big_flavor_rag import SongRAGSystem
        self.rag_system = SongRAGSystem(self.db_manager, use_clap=True)
        
        # Initialize production server
        await self.production_server.initialize()
        
        logger.info("RAG system and Production server ready")
    
    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for Claude."""
        return [
            # RAG SYSTEM TOOLS (search/retrieval - direct library access)
            {
                "name": "search_by_audio_file",
                "description": "Find songs similar to an uploaded audio file by comparing audio characteristics using AI embeddings. This is the most powerful search tool for finding songs by how they sound.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "audio_path": {
                            "type": "string",
                            "description": "Path to the reference audio file"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        },
                        "similarity_threshold": {
                            "type": "number",
                            "description": "Minimum similarity score 0-1 (default: 0.5)"
                        }
                    },
                    "required": ["audio_path"]
                }
            },
            {
                "name": "search_by_text_description",
                "description": "Find songs matching a text description like 'ambient sleep music' or 'energetic workout beats'. Use this for natural language music queries.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Text description of desired music"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["description"]
                }
            },
            {
                "name": "find_song_by_title",
                "description": "Find songs in the library by title. Use fuzzy matching to find songs even if the title is not exact. This is useful when the user mentions a song title and you need to find similar songs in the library.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Song title to search for (supports partial/fuzzy matching)"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "search_by_tempo_range",
                "description": "Find songs within a specific tempo range (BPM). Perfect for finding songs at a specific speed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "min_tempo": {
                            "type": "number",
                            "description": "Minimum tempo in BPM"
                        },
                        "max_tempo": {
                            "type": "number",
                            "description": "Maximum tempo in BPM"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": []
                }
            },
            {
                "name": "search_hybrid",
                "description": "Search with multiple criteria: audio similarity, text description, tempo range. Most flexible and powerful search option.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "audio_path": {
                            "type": "string",
                            "description": "Optional: path to reference audio file"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional: text description"
                        },
                        "min_tempo": {
                            "type": "number",
                            "description": "Optional: minimum BPM"
                        },
                        "max_tempo": {
                            "type": "number",
                            "description": "Optional: maximum BPM"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum results (default: 10)"
                        }
                    },
                    "required": []
                }
            },
            # PRODUCTION SERVER TOOLS (write/modify)
            {
                "name": "analyze_audio",
                "description": "Extract tempo, key, beats, and other audio features from an audio file. Use this to understand the musical characteristics of a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the audio file to analyze"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "match_tempo",
                "description": "Time-stretch audio to a specific BPM without changing pitch. Perfect for DJ mixing or tempo matching.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to input audio file"
                        },
                        "target_bpm": {
                            "type": "number",
                            "description": "Target tempo in BPM"
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Output path for processed file"
                        }
                    },
                    "required": ["file_path", "target_bpm", "output_path"]
                }
            },
            {
                "name": "create_transition",
                "description": "Create a beat-matched DJ transition between two songs with crossfading.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "song1_path": {
                            "type": "string",
                            "description": "Path to first song"
                        },
                        "song2_path": {
                            "type": "string",
                            "description": "Path to second song"
                        },
                        "transition_duration": {
                            "type": "number",
                            "description": "Transition duration in seconds (default: 8)"
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Output path for transition"
                        }
                    },
                    "required": ["song1_path", "song2_path", "output_path"]
                }
            },
            {
                "name": "apply_mastering",
                "description": "Apply professional mastering to make audio louder and more polished with compression and limiting.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to master"
                        },
                        "target_loudness": {
                            "type": "number",
                            "description": "Target LUFS loudness (default: -14.0)"
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Output path for mastered file"
                        }
                    },
                    "required": ["file_path", "output_path"]
                }
            },
            # EDITING TOOLS (processing raw recordings)
            {
                "name": "trim_silence",
                "description": "Remove silence from beginning and end of audio. Perfect for cleaning up raw recordings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to trim"
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
            },
            {
                "name": "reduce_noise",
                "description": "Remove background noise, hum, hiss, and feedback from audio recordings. Essential for cleaning raw live recordings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to clean"
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
            },
            {
                "name": "correct_pitch",
                "description": "Apply pitch correction to fix wrong notes or tuning issues. Can auto-tune to nearest notes or shift by specific semitones.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to correct"
                        },
                        "semitones": {
                            "type": "number",
                            "description": "Semitones to shift (default: 0 for auto-tune)"
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
            },
            {
                "name": "normalize_audio",
                "description": "Normalize audio levels and apply compression for consistent volume. Important step for production-ready audio.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to normalize"
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
            },
            # INTELLIGENT AUTO-PROCESSING TOOLS
            {
                "name": "analyze_and_recommend_processing",
                "description": "Intelligently analyze audio and get specific recommendations for processing. Detects noise levels, frequency imbalances, leading/trailing noise (not just silence), and suggests optimal settings for cleanup.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to analyze"
                        }
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "auto_clean_recording",
                "description": "Automatically analyze and clean a raw recording with AI-driven parameter selection. Intelligently detects and removes non-musical content (speech, noise, etc.), applies optimal noise reduction, EQ, compression, and mastering. This is the BEST option for processing raw recordings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to raw recording to clean"
                        },
                        "output_path": {
                            "type": "string",
                            "description": "Output path for cleaned file"
                        },
                        "aggressiveness": {
                            "type": "string",
                            "description": "Processing aggressiveness: 'gentle', 'moderate', or 'aggressive' (default: 'moderate')"
                        },
                        "keep_intermediates": {
                            "type": "boolean",
                            "description": "Save intermediate steps for review (default: false)"
                        }
                    },
                    "required": ["file_path", "output_path"]
                }
            },
            {
                "name": "apply_eq",
                "description": "Apply equalizer filters to shape sound - remove mud, add clarity, filter unwanted frequencies. Essential for polishing recordings.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to EQ"
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
            },
            {
                "name": "remove_artifacts",
                "description": "Detect and remove clicks, pops, and digital glitches from audio. Cleans up recording artifacts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to audio file to clean"
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
            },
        ]
    
    async def _perform_hybrid_search(self, tool_input: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining multiple criteria.
        
        This method intelligently combines:
        - Text description search
        - Audio similarity search (if audio_path provided)
        - Tempo range filtering (if min/max tempo provided)
        
        Args:
            tool_input: Dict containing search parameters
        
        Returns:
            List of matching songs
        """
        audio_path = tool_input.get("audio_path")
        description = tool_input.get("description")
        min_tempo = tool_input.get("min_tempo")
        max_tempo = tool_input.get("max_tempo")
        limit = tool_input.get("limit", 10)
        
        # Start with all songs or filtered by description
        if description:
            # Use text description search as base
            results = await self.rag_system.search_by_text_description(
                description=description,
                limit=limit * 3  # Get more results to filter
            )
        elif audio_path:
            # Use audio similarity as base
            import os
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found: {audio_path}")
            results = await self.rag_system.search_by_audio_similarity(
                query_audio_path=audio_path,
                limit=limit * 3
            )
        else:
            # Just use tempo range
            results = await self.rag_system.search_by_tempo_range(
                min_tempo=min_tempo,
                max_tempo=max_tempo,
                limit=limit
            )
            return results
        
        # Apply tempo filtering if specified
        if min_tempo is not None or max_tempo is not None:
            filtered_results = []
            for song in results:
                tempo = song.get('tempo_bpm')
                if tempo is None:
                    continue
                    
                if min_tempo is not None and tempo < min_tempo:
                    continue
                if max_tempo is not None and tempo > max_tempo:
                    continue
                    
                filtered_results.append(song)
            results = filtered_results
        
        # Limit final results
        return results[:limit]
    
    async def _call_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Route tool call to appropriate handler."""
        # Define RAG tools (search/retrieval)
        rag_tools = {
            "search_by_audio_file",
            "search_by_text_description",
            "find_song_by_title",
            "search_by_tempo_range",
            "search_hybrid"
        }
        
        # Define Production tools (audio processing)
        production_tools = {
            "analyze_audio",
            "analyze_and_recommend_processing",
            "auto_clean_recording",
            "match_tempo",
            "create_transition",
            "apply_mastering",
            "trim_silence",
            "reduce_noise",
            "correct_pitch",
            "normalize_audio",
            "apply_eq",
            "remove_artifacts"
        }
        
        logger.info(f"Calling tool: {tool_name}")
        
        try:
            if tool_name in rag_tools:
                # Direct RAG system library calls
                if tool_name == "search_by_audio_file":
                    results = await self.rag_system.search_by_audio_similarity(
                        tool_input["audio_path"],
                        limit=tool_input.get("limit", 10),
                        similarity_threshold=tool_input.get("similarity_threshold", 0.5)
                    )
                    result = {
                        "status": "success",
                        "query_audio": tool_input["audio_path"],
                        "results_count": len(results),
                        "songs": results
                    }
                elif tool_name == "find_song_by_title":
                    results = await self.rag_system.find_song_by_title(
                        tool_input["title"],
                        limit=tool_input.get("limit", 10),
                        fuzzy=True
                    )
                    result = {
                        "status": "success",
                        "query_title": tool_input["title"],
                        "results_count": len(results),
                        "songs": results
                    }
                elif tool_name == "search_by_text_description":
                    results = await self.rag_system.search_by_text_description(
                        tool_input["description"],
                        limit=tool_input.get("limit", 10)
                    )
                    result = {
                        "status": "success",
                        "query": tool_input["description"],
                        "results_count": len(results),
                        "songs": results
                    }
                elif tool_name == "search_by_tempo_range":
                    results = await self.rag_system.search_by_tempo_range(
                        min_tempo=tool_input.get("min_tempo"),
                        max_tempo=tool_input.get("max_tempo"),
                        limit=tool_input.get("limit", 10)
                    )
                    result = {
                        "status": "success",
                        "min_tempo": tool_input.get("min_tempo"),
                        "max_tempo": tool_input.get("max_tempo"),
                        "results_count": len(results),
                        "songs": results
                    }
                elif tool_name == "search_hybrid":
                    # Implement hybrid search using RAG system methods
                    results = await self._perform_hybrid_search(tool_input)
                    result = {
                        "status": "success",
                        "search_criteria": tool_input,
                        "results_count": len(results),
                        "songs": results
                    }
                else:
                    result = {"error": f"Unknown RAG tool: {tool_name}"}
                    
            elif tool_name in production_tools:
                # Route to Production server
                if tool_name == "analyze_audio":
                    result = await self.production_server.analyze_audio(
                        tool_input["file_path"]
                    )
                elif tool_name == "analyze_and_recommend_processing":
                    result = await self.production_server.analyze_and_recommend_processing(
                        tool_input["file_path"]
                    )
                elif tool_name == "auto_clean_recording":
                    result = await self.production_server.auto_clean_recording(
                        tool_input["file_path"],
                        tool_input["output_path"],
                        tool_input.get("aggressiveness", "moderate"),
                        tool_input.get("keep_intermediates", False)
                    )
                elif tool_name == "match_tempo":
                    result = await self.production_server.match_tempo(
                        tool_input["file_path"],
                        tool_input["target_bpm"],
                        tool_input["output_path"]
                    )
                elif tool_name == "create_transition":
                    result = await self.production_server.create_transition(
                        tool_input["song1_path"],
                        tool_input["song2_path"],
                        tool_input.get("transition_duration", 8),
                        tool_input["output_path"]
                    )
                elif tool_name == "apply_mastering":
                    result = await self.production_server.apply_mastering(
                        tool_input["file_path"],
                        tool_input.get("target_loudness", -14.0),
                        tool_input["output_path"]
                    )
                # EDITING TOOLS
                elif tool_name == "trim_silence":
                    result = await self.production_server.trim_silence(
                        tool_input["file_path"],
                        tool_input.get("threshold_db", -40),
                        tool_input["output_path"]
                    )
                elif tool_name == "reduce_noise":
                    result = await self.production_server.reduce_noise(
                        tool_input["file_path"],
                        tool_input.get("noise_profile_duration", 1.0),
                        tool_input.get("reduction_strength", 0.7),
                        tool_input["output_path"]
                    )
                elif tool_name == "correct_pitch":
                    result = await self.production_server.correct_pitch(
                        tool_input["file_path"],
                        tool_input.get("semitones", 0),
                        tool_input.get("auto_tune", False),
                        tool_input["output_path"]
                    )
                elif tool_name == "normalize_audio":
                    result = await self.production_server.normalize_audio(
                        tool_input["file_path"],
                        tool_input.get("target_level_db", -3),
                        tool_input.get("apply_compression", True),
                        tool_input["output_path"]
                    )
                elif tool_name == "apply_eq":
                    result = await self.production_server.apply_eq(
                        tool_input["file_path"],
                        tool_input.get("high_pass_freq", 30),
                        tool_input.get("low_pass_freq"),
                        tool_input.get("boost_freq"),
                        tool_input.get("boost_db", 3),
                        tool_input["output_path"]
                    )
                elif tool_name == "remove_artifacts":
                    result = await self.production_server.remove_artifacts(
                        tool_input["file_path"],
                        tool_input.get("sensitivity", 0.5),
                        tool_input["output_path"]
                    )
                else:
                    result = {"error": f"Unknown production tool: {tool_name}"}
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
            
            logger.info(f"Tool {tool_name} returned successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {"error": str(e)}
    
    async def chat(
        self,
        user_message: str,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send a message to Claude with dual MCP tool access.
        
        Args:
            user_message: User's message
            max_tokens: Maximum tokens in response
        
        Returns:
            Dictionary with response and metadata
        """
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        system_prompt = """You are an expert music assistant for the Big Flavor Band with access to powerful tools:

SEARCH TOOLS (RAG System - direct library access):
- search_by_audio_file: Find songs that SOUND similar (most powerful for sonic matching)
- find_song_by_title: Find songs by title (use this FIRST when user mentions a song name)
- search_by_text_description: Natural language search ("chill jazz", "upbeat workout")
- search_by_tempo_range: Find songs by BPM
- search_hybrid: Combine multiple criteria for best results

PRODUCTION TOOLS (MCP Server - audio processing):
- analyze_audio: Extract tempo, key, beats from audio files
- match_tempo: Time-stretch audio to target BPM (no pitch change)
- create_transition: Create beat-matched DJ transitions with crossfading
- apply_mastering: Professional mastering with compression and limiting

INTELLIGENT AUTO-PROCESSING (MCP Server - AI-driven cleanup):
🌟 BEST FOR RAW RECORDINGS:
- auto_clean_recording: Automatically analyze and clean recordings with AI-driven settings
  * Intelligently detects and removes leading/trailing noise (not just silence - detects speech, noise vs music)
  * Auto-selects optimal noise reduction, EQ, compression, and mastering parameters
  * Aggressiveness levels: 'gentle', 'moderate', 'aggressive'
  * This is the RECOMMENDED tool for processing raw recordings!

- analyze_and_recommend_processing: Get detailed analysis and specific recommendations
  * Detects noise levels, frequency imbalances, non-musical content
  * Provides specific parameter recommendations for manual processing
  * Use this when you want to understand what cleanup is needed

MANUAL EDITING TOOLS (MCP Server - for fine control):
- trim_silence: Remove silence from beginning/end of recordings
- reduce_noise: Remove background noise, hum, hiss, and feedback
- correct_pitch: Fix wrong notes or apply auto-tune
- normalize_audio: Normalize levels and apply compression
- apply_eq: Shape sound with EQ filters (remove mud, add clarity)
- remove_artifacts: Remove clicks, pops, and glitches

CRITICAL RULES:
1. Use search tools to FIND songs, use production/editing tools to MODIFY audio
2. When user mentions a song title, FIRST use find_song_by_title to look it up in the library
3. If find_song_by_title returns results, use the audio_path from those results for similarity searches
4. NEVER make up or hallucinate song information
5. Only recommend songs from actual search results
6. If no results found, tell the user honestly
7. Use your music knowledge to interpret user intent

WORKFLOW FOR RAW RECORDINGS:
🌟 RECOMMENDED: Use auto_clean_recording for best results!
- auto_clean_recording: Let AI analyze and apply optimal settings automatically

MANUAL WORKFLOW (if user wants control):
1. analyze_and_recommend_processing: Get specific recommendations first
2. trim_silence: Clean up the beginning/end (or let auto_clean detect non-music content)
3. reduce_noise: Remove background noise and hum
4. correct_pitch: Fix any tuning issues (if needed)
5. apply_eq: Remove mud (high-pass ~80Hz), add clarity
6. normalize_audio: Even out levels with compression
7. apply_mastering: Final loudness and polish

EXAMPLES:
- "Find sleep music" → search_by_text_description("calm sleep ambient")
- "Find songs like Going to California" → find_song_by_title("Going to California") then search_by_audio_file(result.audio_path)
- "Find songs like this.mp3" → search_by_audio_file("this.mp3")
- "Find 120 BPM songs" → search_by_tempo_range(min=115, max=125)
- "Make this song 128 BPM" → match_tempo(file, 128, output)
- "Create mix of song1 and song2" → create_transition(song1, song2, output)
- "Clean up this raw recording" → auto_clean_recording(file, output, "moderate") 🌟 BEST OPTION
- "Analyze what cleanup is needed" → analyze_and_recommend_processing(file)
- "Remove noise from recording.wav" → reduce_noise(recording.wav, output)
- "Process aggressively" → auto_clean_recording(file, output, "aggressive")

Always be helpful, accurate, and creative in helping users discover and work with music!"""
        
        # Call Claude API with tools
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=self.conversation_history,
                tools=self._get_available_tools()
            )
            
            # Track tokens
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            
            # Handle tool use if needed
            while response.stop_reason == "tool_use":
                # Extract tool calls
                tool_results = []
                assistant_content = []
                
                for block in response.content:
                    if block.type == "text":
                        assistant_content.append(block)
                    elif block.type == "tool_use":
                        assistant_content.append(block)
                        
                        # Execute tool
                        tool_result = await self._call_tool(block.name, block.input)
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result)
                        })
                
                # Add assistant message with tool use
                self.conversation_history.append({
                    "role": "assistant",
                    "content": assistant_content
                })
                
                # Add tool results
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })
                
                # Continue conversation
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=self.conversation_history,
                    tools=self._get_available_tools()
                )
                
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens
            
            # Extract final text response
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response.content
            })
            
            return {
                "response": final_text,
                "stop_reason": response.stop_reason,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                },
                "total_cost": self._estimate_cost()
            }
            
        except Exception as e:
            logger.error(f"Error in chat: {e}")
            return {
                "response": f"Error: {str(e)}",
                "error": str(e),
                "total_cost": self._estimate_cost()
            }
    
    def _estimate_cost(self) -> Dict[str, float]:
        """Estimate API costs based on token usage."""
        input_cost = (self.total_input_tokens / 1_000_000) * 0.25
        output_cost = (self.total_output_tokens / 1_000_000) * 1.25
        total_cost = input_cost + output_cost
        
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "input_cost_usd": round(input_cost, 4),
            "output_cost_usd": round(output_cost, 4),
            "total_cost_usd": round(total_cost, 4)
        }
    
    def reset_conversation(self):
        """Reset conversation history."""
        self.conversation_history = []
        logger.info("Conversation history reset")


async def main():
    """Test the Big Flavor Agent."""
    agent = BigFlavorAgent()
    await agent.initialize()
    
    print("\n=== Big Flavor Band RAG+MCP Agent ===")
    print("Type 'quit' to exit, 'reset' to clear conversation\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() == 'quit':
                break
            elif user_input.lower() == 'reset':
                agent.reset_conversation()
                print("Conversation reset.\n")
                continue
            elif not user_input:
                continue
            
            # Get response
            result = await agent.chat(user_input)
            
            print(f"\nAssistant: {result['response']}\n")
            
            # Show token usage
            cost = result['total_cost']
            print(f"[Tokens: {cost['total_tokens']} | Cost: ${cost['total_cost_usd']:.4f}]\n")
            
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
