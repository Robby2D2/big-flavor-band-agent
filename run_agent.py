#!/usr/bin/env python3
"""
Big Flavor Band Agent - Main Entry Point
Run the Claude AI agent with RAG search and MCP production tools
"""

import sys
from pathlib import Path

# Add src and database to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "database"))

# Now import the agent
from src.agent.big_flavor_agent import BigFlavorAgent
import asyncio


async def main():
    """Run the Big Flavor Band agent."""
    agent = BigFlavorAgent()
    await agent.initialize()
    
    print("\n" + "=" * 60)
    print("🎵 Big Flavor Band Agent 🎵")
    print("=" * 60)
    print("\nSearch your music library with natural language!")
    print("Type 'quit' to exit, 'reset' to clear conversation\n")
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if user_input.lower() == 'quit':
                print("\n👋 Goodbye!\n")
                break
            elif user_input.lower() == 'reset':
                agent.reset_conversation()
                print("\n🔄 Conversation reset.\n")
                continue
            elif not user_input:
                continue
            
            # Get response from agent
            result = await agent.chat(user_input)
            
            print(f"\n🤖 Assistant: {result['response']}\n")
            
            # Show token usage
            cost = result['total_cost']
            print(f"💰 [Tokens: {cost['total_tokens']} | Cost: ${cost['total_cost_usd']:.4f}]\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!\n")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}\n")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
