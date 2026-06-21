"""
Process-external store for live radio state (issue #2).

Radio queue / now-playing / play-pause / position and the active-listener set used
to live in per-process in-memory dicts in backend_api.py, so a backend restart wiped
them and two replicas diverged. This store backs that state with PostgreSQL (a single
JSONB row plus a listeners table) so it survives restarts and is shared across
backend instances.
"""

import json
import logging
import time
from typing import Any, Dict

from .database import DatabaseManager

logger = logging.getLogger("radio_state_store")

# Default shape of the radio state, matching what the radio endpoints expect.
DEFAULT_STATE: Dict[str, Any] = {
    "current_song": None,
    "queue": [],
    "is_playing": False,
    "position": 0,
    "last_update": 0.0,
}


def default_state() -> Dict[str, Any]:
    """A fresh copy of the default radio state."""
    state = dict(DEFAULT_STATE)
    state["queue"] = []
    state["last_update"] = time.time()
    return state


class RadioStateStore:
    """Load/save radio state and track listeners in PostgreSQL via DatabaseManager."""

    LISTENER_TTL_SECONDS = 10

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    async def ensure_initialized(self) -> None:
        """Ensure the single radio_state row exists. Idempotent."""
        query = """
            INSERT INTO radio_state (id, state)
            VALUES (1, $1::jsonb)
            ON CONFLICT (id) DO NOTHING
        """
        async with self.db.pool.acquire() as conn:
            await conn.execute(query, json.dumps(default_state()))

    async def load_state(self) -> Dict[str, Any]:
        """Return the current radio state, seeding the default row if missing."""
        query = "SELECT state FROM radio_state WHERE id = 1"
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(query)

        if not row:
            state = default_state()
            await self.save_state(state)
            return state

        raw = row["state"]
        # asyncpg returns jsonb as a str unless a codec is set; handle both.
        state = json.loads(raw) if isinstance(raw, str) else dict(raw)
        # Backfill any keys missing from older rows.
        for key, value in DEFAULT_STATE.items():
            state.setdefault(key, value)
        return state

    async def save_state(self, state: Dict[str, Any]) -> None:
        """Persist the full radio state."""
        query = """
            INSERT INTO radio_state (id, state, updated_at)
            VALUES (1, $1::jsonb, CURRENT_TIMESTAMP)
            ON CONFLICT (id) DO UPDATE
            SET state = EXCLUDED.state,
                updated_at = CURRENT_TIMESTAMP
        """
        async with self.db.pool.acquire() as conn:
            await conn.execute(query, json.dumps(state))

    # Listener tracking ---------------------------------------------------

    async def register_listener(self, listener_id: str) -> None:
        """Mark a listener active (upsert its last-ping timestamp)."""
        query = """
            INSERT INTO radio_listeners (listener_id, last_ping)
            VALUES ($1, CURRENT_TIMESTAMP)
            ON CONFLICT (listener_id) DO UPDATE
            SET last_ping = CURRENT_TIMESTAMP
        """
        async with self.db.pool.acquire() as conn:
            await conn.execute(query, listener_id)

    async def cleanup_stale_listeners(self) -> int:
        """Drop listeners that haven't pinged within the TTL. Returns rows removed."""
        query = f"""
            DELETE FROM radio_listeners
            WHERE last_ping < CURRENT_TIMESTAMP - INTERVAL '{self.LISTENER_TTL_SECONDS} seconds'
        """
        async with self.db.pool.acquire() as conn:
            result = await conn.execute(query)
        # asyncpg returns e.g. "DELETE 3"
        try:
            return int(result.split()[-1])
        except (ValueError, IndexError):
            return 0

    async def count_active_listeners(self) -> int:
        """Number of currently-active listeners (after TTL cleanup is the caller's job)."""
        query = "SELECT COUNT(*) AS n FROM radio_listeners"
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(query)
        return int(row["n"]) if row else 0
