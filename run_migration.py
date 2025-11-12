"""Run database migration"""
import asyncio
from pathlib import Path
from database import DatabaseManager

async def run_migration():
    db = DatabaseManager()
    await db.connect()

    # Read migration file
    migration_file = Path('database/sql/migrations/05-create-users-table.sql')
    sql = migration_file.read_text()

    # Execute migration
    print(f"Running migration: {migration_file.name}")
    async with db.pool.acquire() as conn:
        await conn.execute(sql)
    print("Migration completed successfully!")

    await db.close()

if __name__ == '__main__':
    asyncio.run(run_migration())
