"""
FastAPI backend server for BigFlavor Band Agent
Bridges the Next.js frontend with the Python agent

This module wires the app together: it configures logging, creates the FastAPI
app with a lifespan that owns the long-lived singletons and the radio background
clock, registers the centralized error handlers, configures CORS, and mounts the
per-concern routers (admin, search, agent, radio, tools).

The domain logic lives in ``src/api/``:
- routing in ``src/api/routers/``,
- radio playback/queue/listener logic + playlist writing in ``src/api/radio_service.py``,
- the shared startup singletons, dependencies, and request models in ``src/api/dependencies.py``.
"""
import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.agent.big_flavor_agent import BigFlavorAgent
from src.rag.big_flavor_rag import SongRAGSystem
from src.api_errors import register_error_handlers
from database import DatabaseManager

from src.api import dependencies as deps
from src.api.routers import admin, search, agent as agent_router, radio, tools, produce
from src.api.radio_service import radio_background_loop, set_published_version_paths

# Re-exported so the in-repo tests can import these names off this module (the
# domain logic now lives in src/api/* but the tests target the public surface
# here). See tests/test_blocking_io.py and tests/test_radio_clock.py.
from src.api.radio_service import (  # noqa: F401
    PLAYLIST_FILE,
    AUDIO_LIBRARY_DIR,
    RADIO_TICK_INTERVAL,
    RADIO_TOPUP_EVERY_TICKS,
    _build_and_write_playlist,
    _find_audio_file,
    write_playlist_file,
    update_radio_position,
    advance_to_next_song,
    auto_populate_queue,
    register_listener,
)
from src.api.dependencies import (  # noqa: F401
    get_agent,
    get_rag,
    get_db,
    get_radio_store,
)


class JsonLogFormatter(logging.Formatter):
    """Emit each log record as a single JSON object for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure leveled backend logging.

    LOG_LEVEL  controls verbosity (default INFO).
    LOG_FORMAT selects 'text' (default, human-readable) or 'json' (production).
    """
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler()
    if os.getenv("LOG_FORMAT", "text").lower() == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


configure_logging()
logger = logging.getLogger("backend-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the agent/RAG/DB singletons and start the radio background
    clock/top-up task at startup; release them all at shutdown.

    The singletons live in src.api.dependencies (every router depends on the
    accessors there); we construct them once here so the first request never
    pays cold-start and concurrent first requests can't race an unlocked init.
    """
    logger.info("Startup: initializing backend singletons...")

    deps.db_manager = DatabaseManager()
    await deps.db_manager.connect()
    logger.info("Startup: DatabaseManager connected")

    # Ensure the song_versions table exists and seed the published-version path
    # overrides so the radio/stream serve published cleaned takes (issue #30).
    await deps.db_manager.ensure_song_versions_table()
    set_published_version_paths(await deps.db_manager.get_published_audio_paths())
    logger.info("Startup: song_versions ensured, published-version overrides loaded")

    deps.rag = SongRAGSystem(deps.db_manager, use_clap=True)
    logger.info("Startup: SongRAGSystem ready")

    deps.agent = BigFlavorAgent()
    await deps.agent.initialize()
    logger.info("Startup: BigFlavorAgent initialized")

    # Start the radio clock only after the DB is up — the loop loads/saves radio
    # state through the store, which needs the connected db_manager.
    deps.radio_task = asyncio.create_task(radio_background_loop())
    logger.info("Startup: radio background loop scheduled")

    logger.info("Startup complete: backend ready to serve requests")

    yield

    logger.info("Shutdown: closing backend resources...")
    if deps.radio_task is not None:
        deps.radio_task.cancel()
        try:
            await deps.radio_task
        except asyncio.CancelledError:
            pass
        logger.info("Shutdown: radio background loop stopped")
    # The agent owns its own DatabaseManager (created in BigFlavorAgent.initialize()),
    # so close that pool too, not just the backend's.
    if deps.agent is not None and getattr(deps.agent, "db_manager", None) is not None:
        await deps.agent.db_manager.close()
        logger.info("Shutdown: agent DatabaseManager pool closed")
    if deps.db_manager is not None:
        await deps.db_manager.close()
        logger.info("Shutdown: DatabaseManager pool closed")
    deps.agent = None
    deps.rag = None
    deps.db_manager = None
    deps.radio_task = None
    logger.info("Shutdown complete: backend resources released")


app = FastAPI(title="BigFlavor Band Agent API", version="1.0.0", lifespan=lifespan)

# Centralized error handling: keep raw exception detail in the server logs only,
# and return a consistent, client-safe body for every error class.
register_error_handlers(app)

# CORS middleware for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount the per-concern routers.
app.include_router(admin.router)
app.include_router(search.router)
app.include_router(agent_router.router)
app.include_router(radio.router)
app.include_router(tools.router)
app.include_router(produce.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
