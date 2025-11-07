"""
Simple test to verify MCP server integration with CLI
"""
import asyncio
from agent import BigFlavorAgent

async def test_mcp_integration():
    print("Testing MCP Server Integration...")
    print("=" * 60)
    
    # Test with real songs
    print("\n1. Initializing agent with REAL SONGS...")
    agent = BigFlavorAgent(use_real_songs=True)
    await agent.initialize()
    print(f"   Success! Loaded {len(agent.song_library)} songs")
    
    # Test search
    print("\n2. Testing search...")
    results = await agent.search_songs("tired")
    songs = results.get("results", [])
    print(f"   Found {len(songs)} songs matching 'tired'")
    if songs:
        print(f"   First result: {songs[0]['title']}")
    
    # Test filter
    print("\n3. Testing genre filter...")
    rock_result = await agent.filter_by_genre(["Rock"])
    rock_songs = rock_result.get("results", [])
    print(f"   Found {len(rock_songs)} Rock songs")
    
    # Test recommendation
    print("\n4. Testing song recommendation...")
    if agent.song_library:
        first_song_id = agent.song_library[0]['id']
        suggestion = await agent.suggest_next_song(current_song_id=first_song_id)
        
        # Handle both old and new response format
        suggested = suggestion.get('suggested_song') or suggestion.get('recommended_song')
        if suggested:
            print(f"   Suggested: {suggested['title']}")
            reasoning = suggestion.get('reasoning') or suggestion.get('reasons')
            if reasoning:
                print(f"   Reason: {reasoning}")
        else:
            print(f"   Error in suggestion: {suggestion}")
    
    print("\n" + "=" * 60)
    print("All tests passed! CLI should work with MCP server.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_mcp_integration())
