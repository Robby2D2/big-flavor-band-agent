"""
Demo script showing song IDs in CLI output
"""
import asyncio
from agent import BigFlavorAgent

async def demo_song_ids():
    print("=" * 70)
    print("DEMO: Song IDs in CLI Output")
    print("=" * 70)
    
    # Initialize agent
    print("\nInitializing agent with real songs...")
    agent = BigFlavorAgent(use_real_songs=True)
    await agent.initialize()
    print(f"Loaded {len(agent.song_library)} songs from bigflavorband.com\n")
    
    # Show first 5 songs with IDs
    print("=" * 70)
    print("Sample: First 5 Songs (as they appear in CLI)")
    print("=" * 70)
    for i, song in enumerate(agent.song_library[:5], 1):
        print(f"  {i}. {song['title']} ({song['genre']}, {song.get('mood', 'N/A')}) [ID: {song['id']}]")
    
    # Show recommendation with ID
    print("\n" + "=" * 70)
    print("Sample: Song Recommendation (with ID)")
    print("=" * 70)
    suggestion = await agent.suggest_next_song(current_song_id=agent.song_library[0]['id'])
    suggested = suggestion.get('suggested_song') or suggestion.get('recommended_song')
    if suggested:
        print(f"\n✨ Recommended: {suggested['title']} [ID: {suggested['id']}]")
        print(f"   Genre: {suggested['genre']}")
        reasoning = suggestion.get('reasoning', 'Good match')
        print(f"   Reason: {reasoning}")
    
    # Show detailed view
    print("\n" + "=" * 70)
    print("Sample: Detailed Song View (as in 'List all songs')")
    print("=" * 70)
    sample_song = agent.song_library[0]
    print(f"1. {sample_song['title']} [ID: {sample_song['id']}]")
    print(f"   Genre: {sample_song['genre']} | Mood: {sample_song.get('mood', 'N/A')} | Energy: {sample_song.get('energy', 'N/A')}")
    tempo_str = f"{sample_song['tempo_bpm']} BPM" if sample_song.get('tempo_bpm') else "N/A"
    key_str = sample_song.get('key', 'N/A')
    print(f"   Tempo: {tempo_str} | Key: {key_str}")
    print(f"   Quality: {sample_song.get('audio_quality', 'unknown')}")
    
    print("\n" + "=" * 70)
    print("Benefits of including Song IDs:")
    print("=" * 70)
    print("  ✓ Easy to identify specific song versions (e.g., 'So Tired' has 45+ variants)")
    print("  ✓ Can reference exact songs in discussions or documentation")
    print("  ✓ Useful for API calls or direct song lookups")
    print("  ✓ Helps distinguish between similar titles with different sessions/takes")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(demo_song_ids())
