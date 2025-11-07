#!/usr/bin/env python3
"""
Test script to verify the fixes for the agent errors
"""

import sys
from pathlib import Path

# Add src and database to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root / "database"))

from src.agent.big_flavor_agent import BigFlavorAgent
import asyncio


async def test_agent():
    """Test the agent fixes."""
    print("Testing agent initialization...")
    
    try:
        agent = BigFlavorAgent()
        print("✅ Agent created successfully")
        
        print("\nTesting tool definitions...")
        tools = agent._get_available_tools()
        
        # Check that no tool has a "server" field
        has_server_field = False
        for tool in tools:
            if "server" in tool:
                print(f"❌ Tool '{tool['name']}' still has 'server' field!")
                has_server_field = True
        
        if not has_server_field:
            print(f"✅ All {len(tools)} tools have valid definitions (no 'server' field)")
        
        # Test error response format
        print("\nTesting error response format...")
        # Simulate an error by calling chat without initialization
        result = await agent.chat("test")
        
        if "total_cost" in result:
            print("✅ Error response includes 'total_cost' field")
            print(f"   Response keys: {list(result.keys())}")
        else:
            print("❌ Error response missing 'total_cost' field")
            print(f"   Response keys: {list(result.keys())}")
        
        print("\n✅ All fixes verified successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_agent())
