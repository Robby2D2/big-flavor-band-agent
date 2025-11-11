"""Quick check for tempo_bpm values in database"""
import asyncio
from database.database import DatabaseManager

async def main():
    db = DatabaseManager()
    await db.connect()
    
    result = await db.pool.fetchrow("""
        SELECT 
            COUNT(*) as total,
            COUNT(tempo_bpm) as with_tempo
        FROM songs
    """)
    
    print(f"\nTotal songs: {result['total']}")
    print(f"Songs with tempo_bpm: {result['with_tempo']}")
    print(f"Songs missing tempo_bpm: {result['total'] - result['with_tempo']}")
    
    await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
