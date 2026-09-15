"""Run a database migration.

Usage:
    python scripts/run_migration.py 13-create-user-invites-table.sql
"""
import asyncio
import sys
from pathlib import Path

# Allow running from anywhere: put the repo root (scripts/ -> ..) on the path
# so `database` imports resolve and repo-relative paths below work.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager

MIGRATIONS_DIR = REPO_ROOT / 'database/sql/migrations'


async def run_migration(name):
    # Migration files are anchored to the repo root, not the current directory
    migration_file = MIGRATIONS_DIR / name
    if not migration_file.is_file():
        print(f"No such migration: {name}")
        print("Available:")
        for available in sorted(MIGRATIONS_DIR.glob('*.sql')):
            print(f"  {available.name}")
        raise SystemExit(1)

    sql = migration_file.read_text()

    db = DatabaseManager()
    await db.connect()

    print(f"Running migration: {migration_file.name}")
    async with db.pool.acquire() as conn:
        await conn.execute(sql)
    print("Migration completed successfully!")

    await db.close()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/run_migration.py <migration-file.sql>")
    asyncio.run(run_migration(sys.argv[1]))
