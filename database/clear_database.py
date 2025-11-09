"""
Clear database and reapply schema
"""

import asyncio
import asyncpg
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_and_recreate():
    """Drop all tables and recreate schema"""
    
    # Connection parameters
    conn_params = {
        "host": "localhost",
        "port": 5432,
        "database": "bigflavor",
        "user": "bigflavor",
        "password": "bigflavor_dev_pass"
    }
    
    conn = None
    try:
        # Connect to database
        conn = await asyncpg.connect(**conn_params)
        logger.info("Connected to database")
        
        # Get list of all tables
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)
        
        logger.info(f"Found tables: {[t['table_name'] for t in tables]}")
        
        # Drop all tables in cascade to remove dependencies
        logger.info("Dropping all tables...")
        for table in tables:
            table_name = table['table_name']
            logger.info(f"  Dropping {table_name}...")
            await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
        logger.info("All tables dropped")
        
        # Read and apply schema
        schema_file = Path(__file__).parent / "sql" / "init" / "01-init-schema.sql"
        logger.info(f"Reading schema from: {schema_file}")
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        logger.info("Applying schema...")
        await conn.execute(schema_sql)
        logger.info("Schema applied successfully")
        
        # Verify tables exist
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        
        logger.info(f"Tables created: {[t['table_name'] for t in tables]}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    finally:
        if conn:
            await conn.close()
            logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(clear_and_recreate())
