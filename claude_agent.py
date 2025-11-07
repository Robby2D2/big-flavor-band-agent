"""
Big Flavor Band Agent with Claude 3 Haiku
Uses Claude 3 Haiku LLM with RAG-powered MCP server for intelligent music discovery.
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

# Load environment variables from .env file
load_dotenv()

# Import database for accessing real songs
try:
    from database import DatabaseManager
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False
    logger = logging.getLogger("claude-agent")
    logger.warning("Database not available - will use limited functionality")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("claude-agent")


class ClaudeMusicAgent:
    """
    AI Agent powered by Claude 3 Haiku that uses MCP server tools
    for intelligent music discovery and recommendations.
    """
    
    def __init__(self, api_key: Optional[str] = None, load_songs: bool = True):
        """
        Initialize Claude agent.
        
        Args:
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
            load_songs: Whether to load real songs from database
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        self.client = Anthropic(api_key=self.api_key)
        self.model = "claude-3-haiku-20240307"  # Claude 3 Haiku
        self.conversation_history = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.song_library = []
        self.db_manager = None
        
        logger.info(f"Claude Music Agent initialized with model: {self.model}")
        
        # Load real songs if database is available
        if load_songs and DATABASE_AVAILABLE:
            asyncio.create_task(self._load_songs())
    
    async def _load_songs(self):
        """Load songs from database."""
        try:
            self.db_manager = DatabaseManager()
            await self.db_manager.connect()
            
            async with self.db_manager.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT id, title, genre, audio_url 
                    FROM songs 
                    ORDER BY title
                    LIMIT 1500
                """)
                
                self.song_library = [dict(row) for row in rows]
                logger.info(f"Loaded {len(self.song_library)} songs from database")
                
        except Exception as e:
            logger.error(f"Failed to load songs from database: {e}")
            self.song_library = []
    
    def _estimate_cost(self) -> Dict[str, float]:
        """
        Estimate API costs based on token usage.
        Claude 3 Haiku pricing: $0.25/MTok input, $1.25/MTok output
        
        Returns:
            Dictionary with cost breakdown
        """
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
        """Reset conversation history and token counters."""
        self.conversation_history = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        logger.info("Conversation reset")
    
    async def chat(
        self, 
        user_message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        Send a message to Claude and get a response.
        
        Args:
            user_message: User's message
            system_prompt: Optional system prompt (uses default if not provided)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0-1)
        
        Returns:
            Dictionary with response and metadata
        """
        if system_prompt is None:
            system_prompt = self._get_default_system_prompt()
        
        # Add user message to history
        self.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        try:
            # Call Claude API
            logger.info(f"Sending message to Claude (model: {self.model})")
            
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=self.conversation_history
            )
            
            # Extract response
            assistant_message = response.content[0].text
            
            # Update token counters
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            
            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": assistant_message
            })
            
            # Log token usage
            logger.info(
                f"Response received: {response.usage.input_tokens} input tokens, "
                f"{response.usage.output_tokens} output tokens"
            )
            
            return {
                "status": "success",
                "response": assistant_message,
                "model": self.model,
                "usage": {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "total_tokens": response.usage.input_tokens + response.usage.output_tokens
                },
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
            return {
                "status": "error",
                "error": str(e),
                "type": "unknown_error"
            }
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for music assistant."""
        base_prompt = """You are an expert music assistant for the Big Flavor Band, a talented cover band with an extensive song library.

CRITICAL INSTRUCTIONS:
- You can ONLY recommend songs that exist in the Big Flavor Band's actual catalog
- NEVER make up or hallucinate song names
- If you don't have access to the song list, tell the user you need the song database loaded
- Only suggest songs from the provided song list below

Your capabilities:
- Help users discover songs from the Big Flavor Band's 1,300+ song catalog
- Provide song recommendations based on genre, mood, tempo, and sonic similarity
- Search for songs using the provided song list
- Analyze audio characteristics like tempo (BPM), key, energy, and mood
- Create themed playlists and setlists using ONLY real songs from the catalog
- Answer questions about specific songs from the catalog

Be helpful, enthusiastic, and knowledgeable about music. When users ask for recommendations, explain WHY you're suggesting certain songs based on their characteristics.

REMEMBER: Only recommend songs that appear in the song list provided to you. Do not invent song names."""

        # Add actual song list if available
        if self.song_library:
            song_list = "\n\n=== BIG FLAVOR BAND SONG CATALOG ===\n"
            song_list += f"Total songs available: {len(self.song_library)}\n\n"
            
            # Add a sample of songs (limit to avoid token limits)
            # Group by genre for easier reference
            by_genre = {}
            for song in self.song_library[:500]:  # Limit to 500 songs to save tokens
                genre = song.get('genre', 'Unknown')
                if genre not in by_genre:
                    by_genre[genre] = []
                by_genre[genre].append(f"- {song['title']}")
            
            for genre, songs in sorted(by_genre.items()):
                song_list += f"\n{genre} Songs:\n"
                song_list += "\n".join(songs[:30])  # Limit songs per genre
                if len(songs) > 30:
                    song_list += f"\n... and {len(songs) - 30} more {genre} songs"
                song_list += "\n"
            
            if len(self.song_library) > 500:
                song_list += f"\n\n(Showing first 500 of {len(self.song_library)} total songs)"
            
            base_prompt += song_list
        else:
            base_prompt += "\n\n⚠️  WARNING: Song database not yet loaded. Ask user to wait for songs to load or suggest they restart with database connection."
        
        return base_prompt

    async def discover_similar_songs(
        self,
        song_query: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Use Claude to help discover similar songs through natural conversation.
        
        Args:
            song_query: Natural language query (e.g., "songs like Summer Groove")
            limit: Number of recommendations
        
        Returns:
            Dictionary with recommendations
        """
        prompt = f"""Help me find {limit} songs similar to: "{song_query}"

Please:
1. Understand what the user is looking for
2. Explain your search strategy
3. Provide {limit} song recommendations with brief explanations of why they're similar

Focus on sonic similarity (how they sound) rather than just genre or mood."""
        
        return await self.chat(prompt)
    
    async def create_playlist(
        self,
        theme: str,
        song_count: int = 10
    ) -> Dict[str, Any]:
        """
        Ask Claude to create a themed playlist.
        
        Args:
            theme: Playlist theme (e.g., "upbeat party songs", "chill afternoon vibes")
            song_count: Number of songs
        
        Returns:
            Dictionary with playlist
        """
        prompt = f"""Create a {song_count}-song playlist with the theme: "{theme}"

Please:
1. Understand the mood and characteristics of this theme
2. Select {song_count} songs from the Big Flavor Band catalog
3. Explain why each song fits the theme
4. Consider flow and cohesion between songs"""
        
        return await self.chat(prompt)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the current session.
        
        Returns:
            Dictionary with session statistics
        """
        return {
            "messages_sent": len([m for m in self.conversation_history if m["role"] == "user"]),
            "messages_received": len([m for m in self.conversation_history if m["role"] == "assistant"]),
            "cost_estimate": self._estimate_cost(),
            "model": self.model
        }
    
    def print_cost_summary(self):
        """Print a summary of API costs for this session."""
        costs = self._estimate_cost()
        print("\n" + "=" * 60)
        print("💰 Claude API Cost Summary")
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
    """Run an interactive demo with Claude."""
    print("\n" + "=" * 80)
    print("🎸 Big Flavor Band - Claude 3 Haiku Music Agent")
    print("=" * 80)
    print("\nThis agent uses Claude 3 Haiku ($0.25/MTok input, $1.25/MTok output)")
    print("to help you discover and explore the Big Flavor Band's song library.")
    print("\nCommands:")
    print("  - Type your question or request")
    print("  - 'cost' - Show cost summary")
    print("  - 'reset' - Reset conversation")
    print("  - 'quit' - Exit")
    print("=" * 80 + "\n")
    
    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY environment variable not set!")
        print("\nTo set it:")
        print("  Windows: $env:ANTHROPIC_API_KEY='your-api-key-here'")
        print("  Linux/Mac: export ANTHROPIC_API_KEY='your-api-key-here'")
        return
    
    try:
        # Initialize agent (without auto-loading)
        agent = ClaudeMusicAgent(load_songs=False)
        
        # Load songs
        print("📚 Loading Big Flavor Band song catalog...")
        await agent._load_songs()
        
        if agent.song_library:
            print(f"✅ Loaded {len(agent.song_library)} songs!\n")
        else:
            print("⚠️  No songs loaded - agent will have limited functionality\n")
        
        # Initial greeting
        print("🤖 Agent: Hi! I'm your Big Flavor Band music assistant powered by Claude 3 Haiku.")
        print("         Ask me to find songs, create playlists, or discover similar music!\n")
        
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
                
                # Send message to Claude
                print("\n🤖 Agent: ", end="", flush=True)
                result = await agent.chat(user_input)
                
                if result["status"] == "success":
                    print(result["response"])
                    print(f"\n💡 Tokens: {result['usage']['total_tokens']} | "
                          f"Cost: ${result['cost_estimate']['total_cost_usd']:.4f}\n")
                else:
                    print(f"❌ Error: {result['error']}\n")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                agent.print_cost_summary()
                break
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
    
    except ValueError as e:
        print(f"❌ {e}")
    finally:
        # Cleanup database connection
        if 'agent' in locals() and agent.db_manager:
            await agent.db_manager.close()
            print("Database connection closed.")


async def example_usage():
    """Example of how to use the Claude agent programmatically."""
    print("\n" + "=" * 80)
    print("Example: Using Claude 3 Haiku for Music Discovery")
    print("=" * 80 + "\n")
    
    # Initialize agent
    agent = ClaudeMusicAgent(load_songs=False)
    
    # Load songs
    print("📚 Loading song catalog...")
    await agent._load_songs()
    print(f"✅ Loaded {len(agent.song_library)} songs\n")
    
    try:
        # Example 1: Find similar songs
        print("📝 Example 1: Finding similar songs")
        print("-" * 80)
        result = await agent.discover_similar_songs("upbeat rock songs with high energy", limit=3)
        if result["status"] == "success":
            print(result["response"])
            print(f"\n💰 Cost so far: ${result['cost_estimate']['total_cost_usd']:.4f}\n")
        
        # Example 2: Create a playlist
        print("\n📝 Example 2: Creating a themed playlist")
        print("-" * 80)
        result = await agent.create_playlist("chill acoustic afternoon vibes", song_count=5)
        if result["status"] == "success":
            print(result["response"])
            print(f"\n💰 Cost so far: ${result['cost_estimate']['total_cost_usd']:.4f}\n")
        
        # Show final cost summary
        agent.print_cost_summary()
    finally:
        # Cleanup
        if agent.db_manager:
            await agent.db_manager.close()


async def main():
    """Main entry point."""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "example":
        await example_usage()
    else:
        await interactive_demo()


if __name__ == "__main__":
    asyncio.run(main())
