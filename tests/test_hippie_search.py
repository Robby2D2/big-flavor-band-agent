import asyncio
from src.rag.big_flavor_rag import SongRAGSystem
from database.database import DatabaseManager

async def test_hippie_search():
    """Test searching for songs with 'hippie' in lyrics"""
    db = DatabaseManager()
    rag = SongRAGSystem(db)
    await rag.initialize()
    
    print("\n" + "="*60)
    print("Testing keyword search for 'hippie'")
    print("="*60 + "\n")
    
    results = await rag.search_lyrics_by_keyword('hippie', 20)
    
    print(f"Found {len(results)} songs with 'hippie' in lyrics\n")
    
    if results:
        for i, song in enumerate(results[:5], 1):
            print(f"{i}. {song['title']}")
            if song.get('lyrics'):
                # Show excerpt around the word
                lyrics = song['lyrics'].lower()
                idx = lyrics.find('hippie')
                if idx != -1:
                    start = max(0, idx - 50)
                    end = min(len(lyrics), idx + 50)
                    excerpt = song['lyrics'][start:end]
                    print(f"   ...{excerpt}...")
            print()
    else:
        print("❌ No songs found with 'hippie' in the lyrics")
        print("\nLet's check if we have any lyrics at all...")
        
        # Check total lyrics count
        async with rag.db.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM text_embeddings WHERE content_type = 'lyrics'"
            )
            print(f"Total lyrics in database: {count}")
            
            # Check a sample
            sample = await conn.fetchrow(
                "SELECT song_id, content FROM text_embeddings WHERE content_type = 'lyrics' LIMIT 1"
            )
            if sample:
                print(f"\nSample lyrics (first 200 chars):")
                print(f"Song ID: {sample['song_id']}")
                print(f"Content: {sample['content'][:200]}...")
    
    await rag.cleanup()

if __name__ == "__main__":
    asyncio.run(test_hippie_search())
