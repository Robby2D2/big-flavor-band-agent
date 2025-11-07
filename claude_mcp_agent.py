"""
Big Flavor Band Agent with Claude 3 Haiku + MCP Integration
Uses Claude 3 Haiku with MCP tools for intelligent music discovery.
"""

import asyncio
import json
import logging
import os
from typing import Optional, List, Dict, Any
from datetime import datetime
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
logger = logging.getLogger("claude-mcp-agent")


class ClaudeMCPAgent:
    """
    Claude 3 Haiku agent integrated with MCP server tools.
    Can use semantic search, RAG, and other MCP tools.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Claude MCP agent.
        
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
        
        # Import MCP server locally
        from mcp_server import BigFlavorMCPServer
        self.mcp_server = BigFlavorMCPServer(enable_rag=True)
        
        logger.info(f"Claude MCP Agent initialized with model: {self.model}")
    
    async def initialize(self):
        """Initialize MCP server and RAG system."""
        logger.info("Initializing MCP server and RAG system...")
        await self.mcp_server.initialize_rag()
        logger.info("MCP server ready")
    
    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available MCP tools for Claude."""
        return [
            {
                "name": "get_song_library",
                "description": "Fetch the complete song library from Big Flavor Band's catalog. Returns all 1,300+ songs with metadata.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                }
            },
            {
                "name": "search_songs",
                "description": "Search for songs by title, genre, mood, or tags using text-based search.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for song title, genre, or mood"
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "semantic_search_by_audio",
                "description": "Find songs that SOUND similar to a reference audio file using AI embeddings. This is the most powerful search tool for finding songs by how they actually sound.",
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
                "name": "get_similar_songs",
                "description": "Find songs similar to a given song using audio embeddings. Perfect for 'more like this' recommendations.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "song_id": {
                            "type": "string",
                            "description": "ID of the reference song"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["song_id"]
                }
            },
            {
                "name": "search_by_tempo_and_similarity",
                "description": "Find songs with specific tempo (BPM) and optionally similar sound characteristics.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target_tempo": {
                            "type": "number",
                            "description": "Target tempo in BPM"
                        },
                        "tempo_tolerance": {
                            "type": "number",
                            "description": "BPM tolerance (default: 10.0)"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["target_tempo"]
                }
            },
            {
                "name": "get_embedding_stats",
                "description": "Get statistics about the RAG system - how many songs are indexed, average tempo, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                }
            },
            {
                "name": "smart_search",
                "description": "Intelligent search that understands natural language queries like 'songs to help me sleep', 'upbeat morning music', 'energetic workout songs'. This is the BEST tool for natural language queries about mood, energy, or use case.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query (e.g., 'relaxing songs for sleep', 'energetic workout music', 'chill morning vibes')"
                        },
                        "limit": {
                            "type": "number",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            },
        ]
    
    async def _call_mcp_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Call an MCP server tool and return the result."""
        logger.info(f"Calling MCP tool: {tool_name} with input: {tool_input}")
        
        try:
            if tool_name == "get_song_library":
                result = await self.mcp_server.get_song_library()
            elif tool_name == "search_songs":
                result = await self.mcp_server.search_songs(tool_input["query"])
            elif tool_name == "semantic_search_by_audio":
                result = await self.mcp_server.semantic_search_by_audio(
                    tool_input["audio_path"],
                    tool_input.get("limit", 10),
                    tool_input.get("similarity_threshold", 0.5)
                )
            elif tool_name == "get_similar_songs":
                result = await self.mcp_server.get_similar_songs(
                    tool_input["song_id"],
                    tool_input.get("limit", 10),
                    tool_input.get("similarity_threshold", 0.5)
                )
            elif tool_name == "search_by_tempo_and_similarity":
                result = await self.mcp_server.search_by_tempo_and_similarity(
                    tool_input["target_tempo"],
                    tool_input.get("reference_audio_path"),
                    tool_input.get("tempo_tolerance", 10.0),
                    tool_input.get("limit", 10)
                )
            elif tool_name == "get_embedding_stats":
                result = await self.mcp_server.get_embedding_stats()
            elif tool_name == "smart_search":
                result = await self.mcp_server.smart_search(
                    tool_input["query"],
                    tool_input.get("limit", 10)
                )
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
            
            logger.info(f"Tool {tool_name} returned successfully")
            return result
            
        except Exception as e:
            logger.error(f"Error calling tool {tool_name}: {e}")
            return {"error": str(e)}
    
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
    
    async def chat(
        self,
        user_message: str,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        Send a message to Claude with MCP tool access.
        
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
        
        system_prompt = """You are an expert music assistant for the Big Flavor Band with access to powerful search tools.

IMPORTANT: You have access to real tools that can search the actual Big Flavor Band catalog:
- smart_search: USE THIS for natural language queries like "songs for sleep", "workout music", etc.
- get_song_library: Get all 1,300+ songs (use sparingly, it's a lot of data)
- search_songs: Text-based search by exact title/genre
- get_similar_songs: Find songs similar to a given song (USE THIS for recommendations!)
- search_by_tempo_and_similarity: Find songs by BPM
- get_embedding_stats: Check system statistics

CRITICAL RULES:
1. For queries like "find songs for [activity/mood]", ALWAYS use smart_search first
2. For "similar to [song]", use search_songs to find the song, then get_similar_songs
3. NEVER make up or hallucinate song names
4. Only recommend songs that you find using the tools
5. If a tool returns no results, tell the user honestly

Examples:
- "songs to help me sleep" → use smart_search with query "sleep"
- "energetic workout songs" → use smart_search with query "energetic workout"
- "songs like Summer Groove" → search_songs "Summer Groove", then get_similar_songs with that ID

Be helpful and enthusiastic, but ONLY suggest songs that the tools actually return!"""
        
        try:
            # Call Claude with tool use
            logger.info(f"Sending message to Claude with {len(self._get_available_tools())} tools available")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=self.conversation_history,
                tools=self._get_available_tools()
            )
            
            # Update token counters
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            
            # Process response and handle tool use
            final_response = ""
            tool_uses = []
            
            for content_block in response.content:
                if content_block.type == "text":
                    final_response += content_block.text
                elif content_block.type == "tool_use":
                    tool_uses.append(content_block)
            
            # If Claude used tools, execute them and continue
            if tool_uses:
                logger.info(f"Claude requested {len(tool_uses)} tool calls")
                
                # Add assistant response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })
                
                # Execute all tool calls
                tool_results = []
                for tool_use in tool_uses:
                    result = await self._call_mcp_tool(tool_use.name, tool_use.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(result, indent=2)
                    })
                
                # Send tool results back to Claude
                self.conversation_history.append({
                    "role": "user",
                    "content": tool_results
                })
                
                # Get final response from Claude
                follow_up = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=self.conversation_history,
                    tools=self._get_available_tools()
                )
                
                # Update tokens
                self.total_input_tokens += follow_up.usage.input_tokens
                self.total_output_tokens += follow_up.usage.output_tokens
                
                # Extract final text
                for block in follow_up.content:
                    if block.type == "text":
                        final_response = block.text
                        break
                
                # Add to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": follow_up.content
                })
            else:
                # No tool use, just add response to history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": response.content
                })
            
            logger.info(f"Response completed: {self.total_input_tokens} input, {self.total_output_tokens} output tokens")
            
            return {
                "status": "success",
                "response": final_response,
                "tools_used": [t.name for t in tool_uses],
                "model": self.model,
                "cost_estimate": self._estimate_cost()
            }
            
        except anthropic.APIError as e:
            logger.error(f"Claude API error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "type": "api_error"
            }
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "error": str(e),
                "type": "unknown_error"
            }
    
    def reset_conversation(self):
        """Reset conversation history."""
        self.conversation_history = []
        logger.info("Conversation reset")
    
    def print_cost_summary(self):
        """Print cost summary."""
        costs = self._estimate_cost()
        print("\n" + "=" * 60)
        print("💰 Claude + MCP Cost Summary")
        print("=" * 60)
        print(f"Model: {self.model}")
        print(f"Total Tokens: {costs['total_tokens']:,}")
        print(f"  - Input:  {costs['input_tokens']:,} tokens")
        print(f"  - Output: {costs['output_tokens']:,} tokens")
        print(f"\nEstimated Cost: ${costs['total_cost_usd']:.4f}")
        print(f"  - Input:  ${costs['input_cost_usd']:.4f}")
        print(f"  - Output: ${costs['output_cost_usd']:.4f}")
        print("=" * 60 + "\n")


async def interactive_demo():
    """Run interactive demo."""
    print("\n" + "=" * 80)
    print("🎸 Big Flavor Band - Claude 3 Haiku + MCP Agent")
    print("=" * 80)
    print("\nClaude can now use MCP tools to search your song library!")
    print("\nCommands:")
    print("  - Type your question (Claude will use tools automatically)")
    print("  - 'cost' - Show cost summary")
    print("  - 'reset' - Reset conversation")
    print("  - 'quit' - Exit")
    print("=" * 80 + "\n")
    
    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not set in .env file!")
        return
    
    try:
        print("🔧 Initializing agent...")
        agent = ClaudeMCPAgent()
        await agent.initialize()
        print("✅ Agent ready!\n")
        
        print("🤖 Claude: Hi! I can search the Big Flavor Band catalog using real tools.")
        print("         Try asking: 'Find me 3 upbeat rock songs' or 'Show me songs similar to [song name]'\n")
        
        while True:
            try:
                user_input = input("You: ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() == 'quit':
                    agent.print_cost_summary()
                    print("👋 Goodbye!")
                    break
                
                if user_input.lower() == 'cost':
                    agent.print_cost_summary()
                    continue
                
                if user_input.lower() == 'reset':
                    agent.reset_conversation()
                    print("✅ Conversation reset!\n")
                    continue
                
                # Send message
                print("\n🤖 Claude: ", end="", flush=True)
                result = await agent.chat(user_input)
                
                if result["status"] == "success":
                    print(result["response"])
                    if result.get("tools_used"):
                        print(f"\n🔧 Tools used: {', '.join(result['tools_used'])}")
                    print(f"💡 Cost: ${result['cost_estimate']['total_cost_usd']:.4f}\n")
                else:
                    print(f"❌ Error: {result['error']}\n")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                agent.print_cost_summary()
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
        
        # Cleanup
        if agent.mcp_server.db_manager:
            await agent.mcp_server.db_manager.close()
    
    except ValueError as e:
        print(f"❌ {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """Main entry point."""
    await interactive_demo()


if __name__ == "__main__":
    asyncio.run(main())
