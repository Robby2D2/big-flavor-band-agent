import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from database import DatabaseManager

async def check():
    db = DatabaseManager()
    await db.connect()
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT embedding FROM text_embeddings WHERE content_type = 'lyrics' LIMIT 1")
        print(f"Type: {type(row['embedding'])}")
        print(f"First 100 chars: {str(row['embedding'])[:100]}")
        print(f"Is list: {isinstance(row['embedding'], list)}")
        if row['embedding']:
            print(f"First element: {row['embedding'][0]}")

asyncio.run(check())
