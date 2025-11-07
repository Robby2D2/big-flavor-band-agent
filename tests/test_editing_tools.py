"""
Test script for audio editing capabilities
Demonstrates the new editing tools for processing raw recordings.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src" / "agent"))
sys.path.insert(0, str(project_root / "src" / "production"))

from big_flavor_agent import BigFlavorAgent


async def test_editing_tools():
    """Test the audio editing tools."""
    
    print("=" * 60)
    print("Big Flavor Band - Audio Editing Tools Test")
    print("=" * 60)
    print()
    
    # Initialize agent
    print("Initializing agent...")
    agent = BigFlavorAgent()
    await agent.initialize()
    print("✓ Agent initialized\n")
    
    # Test queries demonstrating editing capabilities
    test_queries = [
        # Understanding the tools
        "What audio editing tools do you have available?",
        
        # Single tool usage
        "Explain how the noise reduction tool works",
        
        # Workflow query
        "What's the recommended workflow for processing a raw live recording?",
        
        # Practical example
        "I have a raw recording with background noise and some silence at the beginning. What should I do?",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'=' * 60}")
        print(f"Test {i}/{len(test_queries)}")
        print(f"{'=' * 60}")
        print(f"Query: {query}\n")
        
        result = await agent.chat(query)
        
        print(f"Response:\n{result['response']}\n")
        
        # Show token usage
        usage = result['total_cost']
        print(f"[Tokens: {usage['total_tokens']} | Cost: ${usage['total_cost_usd']:.4f}]")
        
        if i < len(test_queries):
            print("\nPress Enter to continue...")
            input()
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)
    print("\nTotal Statistics:")
    cost = agent._estimate_cost()
    print(f"Total Input Tokens: {cost['input_tokens']}")
    print(f"Total Output Tokens: {cost['output_tokens']}")
    print(f"Total Cost: ${cost['total_cost_usd']:.4f}")


async def demo_workflow():
    """
    Demonstrate the complete workflow for processing a raw recording.
    
    NOTE: This is a demonstration only. To actually process audio files,
    you need to provide real file paths.
    """
    
    print("\n" + "=" * 60)
    print("DEMO: Complete Audio Processing Workflow")
    print("=" * 60)
    print()
    print("This demonstrates how the agent would process a raw recording")
    print("through the complete production workflow.\n")
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    demo_query = """
    I have a raw live recording called 'band_jam_session.wav' that needs to be 
    turned into a production-ready track. The recording has:
    - Some silence at the beginning and end
    - Background room noise and AC hum
    - A few wrong notes in the guitar part
    - Uneven volume levels
    
    Can you walk me through the complete process and explain what you would do at each step?
    """
    
    print(f"Query: {demo_query}\n")
    print("Agent Response:")
    print("-" * 60)
    
    result = await agent.chat(demo_query)
    print(result['response'])
    
    print("\n" + "-" * 60)
    cost = result['total_cost']
    print(f"\n[Tokens: {cost['total_tokens']} | Cost: ${cost['total_cost_usd']:.4f}]")


async def main():
    """Main entry point."""
    
    print("\nBig Flavor Band - Audio Editing Test Suite")
    print("=" * 60)
    print("\nOptions:")
    print("1. Test editing tool descriptions")
    print("2. Demo complete workflow")
    print("3. Run both")
    print()
    
    choice = input("Select option (1-3): ").strip()
    
    if choice == "1":
        await test_editing_tools()
    elif choice == "2":
        await demo_workflow()
    elif choice == "3":
        await test_editing_tools()
        print("\n\n")
        await demo_workflow()
    else:
        print("Invalid choice. Exiting.")
        return
    
    print("\n\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
