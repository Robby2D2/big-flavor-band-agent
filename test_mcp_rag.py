"""
Test script for MCP Server with RAG capabilities.
Tests semantic search and similar song discovery.
"""

import asyncio
import json
from pathlib import Path

from mcp_server import BigFlavorMCPServer


async def test_rag_tools():
    """Test RAG-enabled MCP server tools."""
    
    print("=" * 80)
    print("Testing MCP Server with RAG System")
    print("=" * 80)
    
    # Initialize server
    server = BigFlavorMCPServer(enable_rag=True)
    await server.initialize_rag()
    
    if not server.enable_rag or server.rag_system is None:
        print("\n❌ RAG system failed to initialize!")
        print("Make sure your database is running and has embeddings indexed.")
        return
    
    print("\n✅ RAG system initialized successfully!\n")
    
    # Test 1: Get embedding stats
    print("\n" + "=" * 80)
    print("Test 1: Get Embedding Statistics")
    print("=" * 80)
    
    stats_result = await server.get_embedding_stats()
    print(json.dumps(stats_result, indent=2))
    
    if stats_result.get('statistics'):
        stats = stats_result['statistics']
        total_songs = stats.get('total_songs', 0)
        with_embeddings = stats.get('songs_with_audio_embeddings', 0)
        
        if with_embeddings == 0:
            print("\n⚠️  No songs have embeddings yet!")
            print("Run `python index_audio_library.py` to index your audio library.")
            return
        
        print(f"\n📊 {with_embeddings}/{total_songs} songs have audio embeddings")
    
    # Test 2: Find songs without embeddings
    print("\n" + "=" * 80)
    print("Test 2: Find Songs Without Embeddings")
    print("=" * 80)
    
    missing_result = await server.find_songs_without_embeddings()
    if missing_result.get('songs'):
        print(f"\n{missing_result['total_unindexed']} songs need indexing:")
        for i, song in enumerate(missing_result['songs'][:5], 1):
            print(f"  {i}. {song.get('title', 'Unknown')} (ID: {song.get('id')})")
        if missing_result['total_unindexed'] > 5:
            print(f"  ... and {missing_result['total_unindexed'] - 5} more")
    else:
        print("\n✅ All songs are indexed!")
    
    # Test 3: Test semantic audio search (if we have a local audio file)
    print("\n" + "=" * 80)
    print("Test 3: Semantic Audio Search")
    print("=" * 80)
    
    # Look for an audio file in the audio_library directory
    audio_lib = Path("audio_library")
    if audio_lib.exists():
        audio_files = list(audio_lib.glob("*.mp3"))
        if audio_files:
            test_audio = str(audio_files[0])
            print(f"\n🔍 Searching for songs similar to: {audio_files[0].name}")
            
            search_result = await server.semantic_search_by_audio(
                test_audio,
                limit=5,
                similarity_threshold=0.3
            )
            
            if search_result.get('results'):
                print(f"\n✅ Found {len(search_result['results'])} similar songs:\n")
                for i, result in enumerate(search_result['results'], 1):
                    print(f"  {i}. {result.get('title', 'Unknown')} - {result.get('genre', 'Unknown')}")
                    print(f"     Similarity: {result.get('similarity', 0):.3f}")
                    tempo = result.get('tempo_bpm')
                    if tempo is not None:
                        print(f"     Tempo: {tempo:.1f} BPM")
                    print()
            else:
                print(f"\n⚠️  No similar songs found: {search_result.get('error', 'Unknown error')}")
        else:
            print("\n⚠️  No MP3 files found in audio_library directory")
    else:
        print("\n⚠️  audio_library directory not found")
    
    # Test 4: Get similar songs (using first indexed song)
    print("\n" + "=" * 80)
    print("Test 4: Get Similar Songs by ID")
    print("=" * 80)
    
    # Get a song ID from the database
    async with server.db_manager.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT s.id, s.title, s.genre 
            FROM songs s
            INNER JOIN audio_embeddings ae ON s.id = ae.song_id
            LIMIT 1
        """)
    
    if row:
        song_id = row['id']
        print(f"\n🔍 Finding songs similar to: {row['title']} ({row['genre']})")
        
        similar_result = await server.get_similar_songs(
            song_id,
            limit=5,
            similarity_threshold=0.3
        )
        
        if similar_result.get('results'):
            print(f"\n✅ Found {len(similar_result['results'])} similar songs:\n")
            for i, result in enumerate(similar_result['results'], 1):
                print(f"  {i}. {result.get('title', 'Unknown')} - {result.get('genre', 'Unknown')}")
                print(f"     Similarity: {result.get('similarity', 0):.3f}")
                print()
        else:
            print(f"\n⚠️  No similar songs found: {similar_result.get('error', 'Unknown error')}")
    else:
        print("\n⚠️  No indexed songs found in database")
    
    # Test 5: Tempo-based search
    print("\n" + "=" * 80)
    print("Test 5: Search by Tempo")
    print("=" * 80)
    
    print("\n🔍 Searching for songs around 120 BPM...")
    
    tempo_result = await server.search_by_tempo_and_similarity(
        target_tempo=120.0,
        tempo_tolerance=10.0,
        limit=5
    )
    
    if tempo_result.get('results'):
        print(f"\n✅ Found {len(tempo_result['results'])} songs:\n")
        for i, result in enumerate(tempo_result['results'], 1):
            print(f"  {i}. {result.get('title', 'Unknown')} - {result.get('genre', 'Unknown')}")
            tempo = result.get('tempo_bpm')
            if tempo is not None:
                print(f"     Tempo: {tempo:.1f} BPM")
            print()
    else:
        print(f"\n⚠️  No songs found: {tempo_result.get('error', 'Unknown error')}")
    
    # Cleanup
    if server.db_manager:
        await server.db_manager.close()
    
    print("\n" + "=" * 80)
    print("✅ All tests completed!")
    print("=" * 80)


async def main():
    """Run the tests."""
    try:
        await test_rag_tools()
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
