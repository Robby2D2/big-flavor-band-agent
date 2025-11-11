import asyncio
from database.database import DatabaseManager

async def test_hippie_search():
    """Test searching for songs with 'hippie' in lyrics"""
    db = DatabaseManager()
    await db.connect()  # Initialize the pool
    
    print("\n" + "="*60)
    print("Testing keyword search for 'hippie'")
    print("="*60 + "\n")
    
    # Search for 'hippie' in lyrics
    query = """
        SELECT DISTINCT
            s.id,
            s.title,
            te.content as lyrics
        FROM songs s
        JOIN text_embeddings te ON s.id = te.song_id
        WHERE te.content_type = 'lyrics'
        AND te.content ILIKE $1
        ORDER BY s.title
        LIMIT 20
    """
    
    async with db.pool.acquire() as conn:
        results = await conn.fetch(query, '%hippie%')
        
        print(f"Found {len(results)} songs with 'hippie' in lyrics\n")
        
        if results:
            for i, row in enumerate(results[:5], 1):
                print(f"{i}. {row['title']}")
                lyrics = row['lyrics'].lower()
                idx = lyrics.find('hippie')
                if idx != -1:
                    start = max(0, idx - 50)
                    end = min(len(lyrics), idx + 50)
                    excerpt = row['lyrics'][start:end]
                    print(f"   ...{excerpt}...")
                print()
        else:
            print("❌ No songs found with 'hippie' in the lyrics")
            print("\nLet's check if we have any lyrics at all...")
            
            # Check total lyrics count
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM text_embeddings WHERE content_type = 'lyrics'"
            )
            print(f"Total lyrics in database: {count}")
            
            # Check for partial matches
            print("\nSearching for songs with 'hipp' (partial match):")
            partial = await conn.fetch(
                """SELECT title, content FROM songs s 
                   JOIN text_embeddings te ON s.id = te.song_id 
                   WHERE te.content_type = 'lyrics' AND te.content ILIKE '%hipp%' 
                   LIMIT 5"""
            )
            for row in partial:
                print(f"- {row['title']}")
    
    await db.close()

if __name__ == "__main__":
    asyncio.run(test_hippie_search())
