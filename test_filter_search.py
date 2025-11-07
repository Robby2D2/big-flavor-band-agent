"""Test the new search_by_filters with Claude interpreting."""
import asyncio
from mcp_server import BigFlavorMCPServer


async def main():
    server = BigFlavorMCPServer(enable_rag=True)
    await server.initialize_rag()
    
    print("\n" + "=" * 60)
    print("Testing: search_by_filters (Claude's job is to interpret)")
    print("=" * 60)
    
    # Test 1: Sleep songs (Claude would call with tempo_max=90)
    print("\n1. Sleep songs → tempo_max=90")
    result = await server.search_by_filters(tempo_max=90, limit=5)
    print(f"   Found {len(result['songs'])} songs")
    if result['songs']:
        for song in result['songs'][:3]:
            print(f"   - {song['title']} ({song['tempo_bpm']:.1f} BPM)")
    
    # Test 2: Workout songs (Claude would call with tempo_min=120)
    print("\n2. Workout songs → tempo_min=120")
    result = await server.search_by_filters(tempo_min=120, limit=5)
    print(f"   Found {len(result['songs'])} songs")
    if result['songs']:
        for song in result['songs'][:3]:
            print(f"   - {song['title']} ({song['tempo_bpm']:.1f} BPM)")
    
    # Test 3: Chill jazz (Claude would call with genre + tempo)
    print("\n3. Chill jazz → genre='jazz', tempo_max=100")
    result = await server.search_by_filters(genre="jazz", tempo_max=100, limit=5)
    print(f"   Found {len(result['songs'])} songs")
    if result['songs']:
        for song in result['songs'][:3]:
            genre = song['genre'] or 'Unknown'
            print(f"   - {song['title']} - {genre} ({song['tempo_bpm']:.1f} BPM)")
    
    # Test 4: Just genre
    print("\n4. Rock songs → genre='rock'")
    result = await server.search_by_filters(genre="rock", limit=5)
    print(f"   Found {len(result['songs'])} songs")
    if result['songs']:
        for song in result['songs'][:3]:
            genre = song['genre'] or 'Unknown'
            tempo = f"{song['tempo_bpm']:.1f} BPM" if song['tempo_bpm'] else "No tempo"
            print(f"   - {song['title']} - {genre} ({tempo})")
    
    await server.db_manager.close()
    print("\n✅ Tests complete!")


if __name__ == "__main__":
    asyncio.run(main())
