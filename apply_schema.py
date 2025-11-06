"""
Apply database schema updates for web scraping
"""

import asyncio
import logging
from database import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def apply_schema():
    """Apply the schema updates"""
    db = DatabaseManager(
        host="localhost",
        port=5432,
        database="bigflavor",
        user="bigflavor",
        password="bigflavor_dev_pass"
    )
    
    try:
        await db.connect()
        logger.info("Connected to database")
        
        # Read SQL file
        with open('sql/init/02-add-song-details.sql', 'r') as f:
            sql = f.read()
        
        # Split into individual statements
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        
        logger.info(f"Executing {len(statements)} SQL statements...")
        
        async with db.pool.acquire() as conn:
            for i, statement in enumerate(statements, 1):
                try:
                    logger.info(f"Executing statement {i}/{len(statements)}")
                    await conn.execute(statement)
                except Exception as e:
                    # Skip if already exists
                    if "already exists" in str(e).lower():
                        logger.info(f"Statement {i} already applied, skipping")
                    else:
                        logger.error(f"Error executing statement {i}: {e}")
                        raise
        
        logger.info("Schema updates applied successfully!")
        
    except Exception as e:
        logger.error(f"Failed to apply schema: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(apply_schema())
