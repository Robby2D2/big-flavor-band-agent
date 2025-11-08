import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager

async def main():
    db = DatabaseManager()
    await db.connect()
    
    # Check if table exists
    result = await db.pool.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'text_embeddings'"
    )
    print(f"text_embeddings table exists: {len(result) > 0}")
    
    if len(result) > 0:
        # Check columns
        cols = await db.pool.fetch(
            "SELECT column_name FROM information_schema.columns WHERE table_name = 'text_embeddings'"
        )
        print(f"Columns: {[r['column_name'] for r in cols]}")
        
        # Check data
        count = await db.pool.fetchval("SELECT COUNT(*) FROM text_embeddings")
        print(f"Total text_embeddings entries: {count}")
        
        lyrics_count = await db.pool.fetchval(
            "SELECT COUNT(*) FROM text_embeddings WHERE content_type = 'lyrics'"
        )
        print(f"Lyrics entries: {lyrics_count}")
    
    # Check sample songs with audio URLs
    print("\nSample songs:")
    rows = await db.pool.fetch("SELECT id, title, audio_url FROM songs WHERE audio_url IS NOT NULL LIMIT 5")
    for r in rows:
        print(f"  {r['title']}: {r['audio_url']}")
    
    # Check lyrics for 02_requiem_wahwah
    print("\nChecking lyrics for 02_requiem_wahwah:")
    lyrics_row = await db.pool.fetchrow("""
        SELECT te.song_id, s.title, te.content_type, 
               te.content,
               LENGTH(te.content) as content_length,
               te.created_at
        FROM text_embeddings te
        JOIN songs s ON te.song_id = s.id
        WHERE s.id = '02_requiem_wahwah'
        AND te.content_type = 'lyrics'
    """)
    
    if lyrics_row:
        print(f"  ✓ Lyrics found!")
        print(f"    Song ID: {lyrics_row['song_id']}")
        print(f"    Title: {lyrics_row['title']}")
        print(f"    Content length: {lyrics_row['content_length']} characters")
        print(f"    Created: {lyrics_row['created_at']}")
        print(f"\n  Lyrics content:")
        print(f"  {'-'*60}")
        print(f"  {lyrics_row['content']}")
        print(f"  {'-'*60}")
    else:
        print(f"  ✗ No lyrics found for 02_requiem_wahwah")
    
    await db.close()

if __name__ == '__main__':
    asyncio.run(main())
