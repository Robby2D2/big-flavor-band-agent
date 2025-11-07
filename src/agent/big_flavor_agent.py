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
                "server": "rag",
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
                "server": "rag",
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
                "name": "search_by_tempo_range",
                "server": "rag",
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
                "server": "rag",
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
                "server": "mcp",
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
                "server": "mcp",
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
                "server": "mcp",
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
                "server": "mcp",
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
        ]
    
    async def _call_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Route tool call to appropriate handler."""
        # Determine which system handles this tool
        tool_def = next((t for t in self._get_available_tools() if t["name"] == tool_name), None)
        
        if not tool_def:
            return {"error": f"Unknown tool: {tool_name}"}
        
        server_type = tool_def.get("server", "unknown")
        logger.info(f"Calling {server_type} tool: {tool_name}")
        
        try:
            if server_type == "rag":
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
                    
            elif server_type == "mcp":
                # Route to Production server
                if tool_name == "analyze_audio":
                    result = await self.production_server.analyze_audio(
                        tool_input["file_path"]
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
                else:
                    result = {"error": f"Unknown production tool: {tool_name}"}
            else:
                result = {"error": f"Unknown server type: {server_type}"}
            
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
- search_by_text_description: Natural language search ("chill jazz", "upbeat workout")
- search_by_tempo_range: Find songs by BPM
- search_hybrid: Combine multiple criteria for best results

PRODUCTION TOOLS (MCP Server - audio processing):
- analyze_audio: Extract tempo, key, beats from audio files
- match_tempo: Time-stretch audio to target BPM (no pitch change)
- create_transition: Create beat-matched DJ transitions with crossfading
- apply_mastering: Professional mastering with compression and limiting

CRITICAL RULES:
1. Use search tools to FIND songs, use production tools to MODIFY audio
2. NEVER make up or hallucinate song information
3. Only recommend songs from actual search results
4. If no results found, tell the user honestly
5. Use your music knowledge to interpret user intent

EXAMPLES:
- "Find sleep music" → search_by_text_description("calm sleep ambient")
- "Find songs like this.mp3" → search_by_audio_file("this.mp3")
- "Find 120 BPM songs" → search_by_tempo_range(min=115, max=125)
- "Make this song 128 BPM" → match_tempo(file, 128, output)
- "Create mix of song1 and song2" → create_transition(song1, song2, output)

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
                "error": str(e)
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
