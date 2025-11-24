# Big Flavor Band Agent - Claude Code Context

## Docker Development Setup

### Viewing Logs
Backend logs are in the Docker container, not local files:
```bash
docker logs bigflavor-backend --tail 100
docker logs bigflavor-backend -f  # follow logs
```

### Hot Reloading
Source code is mounted as volumes for hot reloading. After code changes, **restart instead of rebuild**:
```bash
docker restart bigflavor-backend
```

Mounted volumes (from docker-compose.yml):
- `.\src:/app/src:ro`
- `.\database:/app/database:ro`
- `.\backend_api.py:/app/backend_api.py:ro`

Only rebuild if you change dependencies (requirements.txt) or Dockerfile.

## Architecture Overview

- **Backend**: Python FastAPI (`backend_api.py`) running in Docker
- **Frontend**: Next.js app in `frontend/` directory
- **Agent**: Claude/Ollama-powered agent in `src/agent/big_flavor_agent.py`
- **RAG System**: Song search in `src/rag/big_flavor_rag.py`
- **Database**: PostgreSQL with pgvector for embeddings

## Key Services

| Container | Purpose |
|-----------|---------|
| bigflavor-backend | Python API + Agent |
| bigflavor-frontend | Next.js web app |
| postgres | Database |
| ollama | Local LLM (qwen2.5:7b) |
| bigflavor-icecast | Streaming server (port 8001:8000) |
| bigflavor-liquidsoap | Audio automation/playlist engine |

## Radio Streaming Architecture

The radio functionality uses Icecast + Liquidsoap for synchronized audio streaming:

- **Backend** (`backend_api.py`): Manages radio queue state, writes playlist file to `streaming/playlist/radio.m3u`
- **Liquidsoap** (`streaming/radio.liq`): Reads playlist, streams audio to Icecast
- **Icecast**: Broadcasts stream at `/stream` endpoint (proxied by nginx)
- **Shared Volume**: `./streaming/playlist` mounted to both backend and liquidsoap containers

### Critical Configuration Details

**Liquidsoap playlist sources MUST use `mksafe()` wrapper:**
```liquidsoap
radio_queue = mksafe(radio_queue)
fallback_music = mksafe(fallback_music)
radio = fallback([radio_queue, fallback_music, blank()])
```

Without `mksafe()`, the fallback operator will incorrectly choose `blank()` even when playlist files exist and are valid. This is because playlist sources can appear "not ready" during initialization.

**File paths in playlist must match Liquidsoap's mount points:**
- Backend writes paths as `/app/audio_library/song.mp3`
- Must convert to `/audio_library/song.mp3` for Liquidsoap container
- See `write_playlist_file()` in `backend_api.py` for path conversion logic

## Common Commands

```bash
# Start all services
docker-compose up -d

# View backend logs
docker logs bigflavor-backend --tail 100

# View Liquidsoap logs (for radio debugging)
docker logs bigflavor-liquidsoap --tail 100
docker exec bigflavor-liquidsoap sh -c "tail -100 /var/log/liquidsoap/radio.log"

# Restart after code changes
docker restart bigflavor-backend

# Frontend dev server
cd frontend && npm run dev
```

## Liquidsoap Configuration Changes (IMPORTANT)

**Problem**: Docker BuildKit aggressively caches the `COPY` layer even when source files change.

**Solution**: When updating `streaming/radio.liq`, you MUST force a rebuild:

```bash
# Touch the file to update timestamp
powershell -Command "(Get-Item 'streaming/radio.liq').LastWriteTime = Get-Date"

# Remove container and rebuild without cache
docker stop bigflavor-liquidsoap
docker rm bigflavor-liquidsoap
docker-compose build --no-cache liquidsoap
docker-compose up -d liquidsoap
```

Simply using `docker restart` or even `docker-compose build` (without `--no-cache`) will NOT pick up configuration changes due to Docker's layer caching on Windows.
