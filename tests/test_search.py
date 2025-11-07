#!/usr/bin/env python3
"""
Test the search functionality with the database fixes
"""

import sys
from pathlib import Path
import asyncio

# Add src and database to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "database"))

from src.agent.big_flavor_agent import BigFlavorAgent


async def test_search():
    """Test search functionality."""
    print("Initializing agent...")
    agent = BigFlavorAgent()
    await agent.initialize()
    print("✅ Agent initialized\n")
    
    # Test text description search
    print("Testing: Find songs for sleep")
    result = await agent.chat("Find 3 songs to help me sleep")
    
    print(f"\n🤖 Response: {result['response']}\n")
    
    if 'error' in result:
        print(f"❌ Error occurred: {result['error']}")
    else:
        print("✅ Search completed successfully!")
    
    # Show token usage
    cost = result['total_cost']
    print(f"💰 [Tokens: {cost['total_tokens']} | Cost: ${cost['total_cost_usd']:.4f}]\n")


if __name__ == "__main__":
    asyncio.run(test_search())
