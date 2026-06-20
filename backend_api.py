"""
FastAPI backend server for BigFlavor Band Agent
Bridges the Next.js frontend with the Python agent

This module wires the app together: it creates the FastAPI app, configures CORS,
and mounts the per-concern routers (search, agent, radio, admin, tools). The
domain logic lives in `src/api/` — routing in `src/api/routers/`, radio
playback/queue state in `src/api/radio_service.py`, and the shared startup
singletons + request models in `src/api/dependencies.py`.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import admin, search, agent as agent_router, radio, tools
# Re-exported for the in-repo tests (tests/test_blocking_io.py), which import
# these names off this module and monkeypatch AUDIO_LIBRARY_DIR here.
from src.api.radio_service import (  # noqa: F401
    PLAYLIST_FILE,
    AUDIO_LIBRARY_DIR,
    _build_and_write_playlist,
    _find_audio_file,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="BigFlavor Band Agent API", version="1.0.0")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
