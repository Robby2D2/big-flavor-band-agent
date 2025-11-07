"""
Example usage script for Big Flavor Band AI Agent
Run this to see the agent in action with various features.
"""

import asyncio
import json
from agent import BigFlavorAgent


async def demo_recommendations():
    """Demonstrate song recommendation features."""
    print("\n" + "="*60)
    print("🎵 SONG RECOMMENDATION DEMO")
    print("="*60)
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Example 1: Next song after Summer Groove
    print("\n1. What should we play after 'Summer Groove'?")
    suggestion = await agent.suggest_next_song(current_song_id="song_001")
    print(f"\n   Recommended: {suggestion['recommended_song']['title']}")
    print(f"   Reasons:")
    for reason in suggestion['reasons']:
        print(f"     • {reason}")
    
    # Example 2: Find similar songs
    print("\n2. What songs are similar to 'Midnight Blues'?")
    similar = await agent.suggest_similar_songs("song_002", limit=3)
    print(f"\n   Similar songs to '{similar['reference_song']['title']}':")
    for song in similar['similar_songs']:
        print(f"     • {song['title']} (similarity: {song['similarity_score']}%)")
    
    # Example 3: Request by mood
    print("\n3. Suggest a relaxed song")
    relaxed = await agent.suggest_next_song(mood="relaxed")
    print(f"\n   Recommended: {relaxed['recommended_song']['title']}")
    print(f"   Mood: {relaxed['recommended_song']['mood']}")


async def demo_album_curation():
    """Demonstrate album curation features."""
    print("\n" + "="*60)
    print("💿 ALBUM CURATION DEMO")
    print("="*60)
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Example 1: Create an upbeat rock album
    print("\n1. Creating an 'upbeat rock' album...")
    album = await agent.create_album_suggestion(theme="upbeat rock", target_duration_minutes=30)
    
    print(f"\n   Album: {album['album_name']}")
    print(f"   Duration: {album['total_duration_minutes']} minutes")
    print(f"   Tracks ({album['track_count']}):")
    for track in album['tracks']:
        print(f"     {track['track_number']}. {track['title']} ({track['duration_seconds']//60}:{track['duration_seconds']%60:02d})")
    
    print(f"\n   Curation Notes:")
    for note in album['curation_notes']:
        print(f"     • {note}")
    
    # Example 2: Analyze album flow
    print("\n2. Analyzing flow of songs...")
    song_ids = ["song_001", "song_003", "song_005"]
    flow_analysis = await agent.analyze_album_flow(song_ids)
    
    print(f"\n   Overall Flow: {flow_analysis['flow_rating'].upper()}")
    print(f"   Score: {flow_analysis['overall_flow_score']}/100")
    
    if flow_analysis['improvement_suggestions']:
        print(f"\n   Suggestions:")
        for suggestion in flow_analysis['improvement_suggestions'][:3]:
            print(f"     • {suggestion}")


async def demo_audio_engineering():
    """Demonstrate audio engineering features."""
    print("\n" + "="*60)
    print("🎚️ AUDIO ENGINEERING DEMO")
    print("="*60)
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Example 1: Get suggestions for a specific song
    print("\n1. Audio engineering suggestions for 'Midnight Blues'...")
    suggestions = await agent.get_audio_engineering_suggestions("song_002")
    
    print(f"\n   Song: {suggestions['song_title']}")
    print(f"   Current Quality: {suggestions['current_quality']}")
    print(f"   Improvement Potential: {suggestions['estimated_improvement_potential']['percentage']}%")
    
    print(f"\n   Priority Actions:")
    for action in suggestions['priority_actions'][:3]:
        print(f"     {action}")
    
    print(f"\n   Mixing Suggestions:")
    for tip in suggestions['improvement_suggestions']['mixing'][:3]:
        print(f"     • {tip}")
    
    # Example 2: Compare song quality
    print("\n2. Comparing audio quality across songs...")
    comparison = await agent.compare_song_quality(["song_001", "song_002", "song_003"])
    
    print(f"\n   Average Quality Score: {comparison['average_quality_score']}/100")
    print(f"\n   Quality Rankings:")
    for rank, song in enumerate(comparison['quality_ranking'][:3], 1):
        print(f"     {rank}. {song['title']} - {song['quality']} ({song['quality_score']}/100)")


async def demo_setlist():
    """Demonstrate setlist creation."""
    print("\n" + "="*60)
    print("🎤 SETLIST GENERATION DEMO")
    print("="*60)
    
    agent = BigFlavorAgent()
    await agent.initialize()
    
    # Example: Create a building energy setlist
    print("\n1. Creating a 45-minute setlist with building energy...")
    setlist = await agent.suggest_setlist(duration_minutes=45, energy_flow="building")
    
    print(f"\n   Setlist: {setlist['setlist_name']}")
    print(f"   Duration: {setlist['duration_minutes']} minutes")
    print(f"   Energy Flow: {setlist['energy_flow']}")
    
    print(f"\n   Songs:")
    for song in setlist['songs']:
        print(f"     {song['position']}. {song['title']}")
        print(f"        Energy: {song['energy']} | Note: {song['performance_notes']}")
    
    print(f"\n   Setlist Notes:")
    for note in setlist['setlist_notes']:
        print(f"     • {note}")


async def main():
    """Run all demos."""
    print("\n")
    print("🎸" * 30)
    print("  BIG FLAVOR BAND AI AGENT - DEMO")
    print("🎸" * 30)
    
    try:
        await demo_recommendations()
        await demo_album_curation()
        await demo_audio_engineering()
        await demo_setlist()
        
        print("\n" + "="*60)
        print("✅ Demo completed successfully!")
        print("="*60)
        print("\nNext steps:")
        print("  • Edit config.json to customize settings")
        print("  • Update mcp_server.py to fetch real song data")
        print("  • Run 'python mcp_server.py' to start the MCP server")
        print("  • Check QUICKSTART.md for more examples")
        print("\nRock on! 🤘\n")
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        print("Check that all dependencies are installed: pip install -r requirements.txt\n")


if __name__ == "__main__":
    asyncio.run(main())
