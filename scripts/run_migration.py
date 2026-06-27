"""Run database migration"""
import asyncio
import sys
from pathlib import Path

# Allow running from anywhere: put the repo root (scripts/ -> ..) on the path
# so `database` imports resolve and repo-relative paths below work.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager

async def run_migration():
    db = DatabaseManager()
    await db.connect()

    # Read migration file (anchored to repo root, not the current directory)
    migration_file = REPO_ROOT / 'database/sql/migrations/05-create-users-table.sql'
    sql = migration_file.read_text()

    # Execute migration
    print(f"Running migration: {migration_file.name}")
    async with db.pool.acquire() as conn:
        await conn.execute(sql)
    print("Migration completed successfully!")

    await db.close()

if __name__ == '__main__':
    asyncio.run(run_migration())
