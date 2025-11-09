"""
Run database migration to convert song IDs to INTEGER
"""
import asyncio
import asyncpg
import os
from pathlib import Path

async def run_migration():
    print("="*70)
    print("Database Migration: Song ID to INTEGER")
    print("="*70)
    print()
    print("WARNING: This will DROP all existing songs and related data!")
    print()
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response not in ['yes', 'y']:
        print("Cancelled.")
        return
    
    # Read migration SQL
    migration_file = Path(__file__).parent / "sql" / "migrations" / "04-migrate-song-id-to-integer.sql"
    with open(migration_file, 'r') as f:
        migration_sql = f.read()
    
    # Connect to database
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    database = os.getenv("DB_NAME", "bigflavor")
    user = os.getenv("DB_USER", "bigflavor")
    password = os.getenv("DB_PASSWORD", "bigflavor_dev_pass")
    
    print("\nConnecting to database...")
    conn = await asyncpg.connect(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password
    )
    
    print("Applying migration...")
    try:
        await conn.execute(migration_sql)
        print("\n✓ Migration applied successfully!")
        print()
        print("Next steps:")
        print("  1. Run the scraper to populate with new data")
        print("  2. Songs will now use numeric IDs from audio URLs")
        print()
    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
