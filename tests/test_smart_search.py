"""Test smart_search functionality."""
import asyncio
from database import DatabaseManager
from mcp_server import BigFlavorMCPServer


async def test_database_tempo():
    """Check if tempo data exists in database."""
    print("=" * 60)
    print("Testing Database Tempo Data")
    print("=" * 60)
    
    db = DatabaseManager()
    await db.connect()
    
    # Check total counts
    async with db.pool.acquire() as conn:
        result = await conn.fetch("""
            SELECT 
                COUNT(*) as total_songs,
                COUNT(ae.song_id) as songs_with_embeddings,
                COUNT(CASE WHEN ae.librosa_features->>'tempo' IS NOT NULL THEN 1 END) as songs_with_tempo
            FROM songs s 
            LEFT JOIN audio_embeddings ae ON s.id = ae.song_id
        """)
        
        print(f"\nDatabase Stats:")
        print(f"  Total songs: {result[0]['total_songs']}")
        print(f"  Songs with embeddings: {result[0]['songs_with_embeddings']}")
        print(f"  Songs with tempo data: {result[0]['songs_with_tempo']}")
        
        # Get slowest songs (best for sleep)
        slow_songs = await conn.fetch("""
            SELECT s.id, s.title, s.genre, (ae.librosa_features->>'tempo')::float as tempo
            FROM songs s 
            JOIN audio_embeddings ae ON s.id = ae.song_id
            WHERE ae.librosa_features->>'tempo' IS NOT NULL
            ORDER BY (ae.librosa_features->>'tempo')::float ASC
            LIMIT 10
        """)
        
        print(f"\n10 Slowest Songs (best for sleep):")
        for song in slow_songs:
            genre = song['genre'] or 'Unknown'
            print(f"  {song['title'][:40]:40} - {genre[:15]:15} - {song['tempo']:6.1f} BPM")
    
    await db.close()


async def test_smart_search():
    """Test the smart_search function."""
    print("\n" + "=" * 60)
    print("Testing Smart Search")
    print("=" * 60)
    
    server = BigFlavorMCPServer(enable_rag=True)
    await server.initialize_rag()
    
    # Test sleep query
    print("\nQuery: 'sleep'")
    result = await server.smart_search("sleep", limit=10)
    print(f"Results: {len(result.get('songs', []))} songs found")
    
    if result.get('songs'):
        print("\nFirst 5 results:")
        for song in result['songs'][:5]:
            print(f"  {song['title'][:40]:40} - {song['genre']:15}")
    else:
        print(f"\nError or no results: {result}")
    
    # Test with different queries
    test_queries = ["relax", "calm", "acoustic", "slow"]
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        result = await server.smart_search(query, limit=5)
        print(f"  Results: {len(result.get('songs', []))} songs")
    
    await server.db_manager.close()


async def main():
    """Run all tests."""
    await test_database_tempo()
    await test_smart_search()


if __name__ == "__main__":
    asyncio.run(main())
