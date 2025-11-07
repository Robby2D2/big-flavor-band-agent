"""
Apply database migration to update search functions with all song fields
"""
import asyncio
import logging
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")


async def apply_migration():
    """Apply the search functions update migration."""
    
    # Read the SQL file
    with open('update_search_functions.sql', 'r') as f:
        migration_sql = f.read()
    
    # Connect to database
    db = DatabaseManager()
    await db.connect()
    
    try:
        # Execute the migration
        async with db.pool.acquire() as conn:
            await conn.execute(migration_sql)
        
        logger.info("✅ Search functions updated successfully!")
        logger.info("The demo_rag_search.py will now show all song information.")
        
    except Exception as e:
        logger.error(f"❌ Error applying migration: {e}")
        raise
    
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(apply_migration())
