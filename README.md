# Big Flavor Band Agent 🎵

AI-powered music discovery and production assistant for the Big Flavor Band's 1,300+ song catalog.

## Architecture

```
┌─────────────────────────────────┐
│     Big Flavor Agent            │
│  (Claude AI + RAG + MCP)        │
└──────┬──────────────────┬───────┘
       │                  │
       │ (direct)         │ (MCP)
       ▼                  ▼
┌─────────────┐     ┌──────────────┐
│ RAG System  │     │Production MCP│
│  (Search)   │     │   Server     │
└─────────────┘     └──────────────┘
```

### Components

- **Agent** (`src/agent/`) - Claude AI orchestration
- **RAG System** (`src/rag/`) - Semantic search library
- **MCP Server** (`src/mcp/`) - Audio production tools
- **Database** (`database/`) - PostgreSQL with pgvector

## Running the stack

The app runs as a set of Docker Compose services (FastAPI backend, Next.js
frontend, PostgreSQL/pgvector, an LLM layer, and an Icecast + Liquidsoap radio
stack). Source directories are mounted as volumes, so most code changes
hot-reload — `docker restart <service>` instead of rebuilding.

### Prerequisites

- Docker Desktop (with Compose)
- An `.env` file: `cp .env.example .env`, then set at least `ANTHROPIC_API_KEY`
  (the project defaults to the Anthropic API — **no local LLM required**)

### Option A — full stack in Docker

```bash
docker-compose up -d            # start everything
docker-compose ps               # check status
docker logs bigflavor-backend -f
```

By default this uses the Anthropic API. (A local Ollama model is still supported
as an opt-in — see [`docs/LOCAL_LLM_GUIDE.md`](docs/LOCAL_LLM_GUIDE.md).)

### Option B — run the web app on the host, infra in Docker

Best for active development of the backend/frontend: Docker provides only the
backing services (PostgreSQL + radio stack) while you run the FastAPI backend and
Next.js frontend on your machine against Anthropic. This is wired up by a Compose
override.

```bash
# One-time: enable the local override (it is gitignored)
cp docker-compose.override.yml.example docker-compose.override.yml

# Start just the backing services + print next steps
pwsh scripts/dev-local.ps1          # or: docker-compose up -d

# Then, in separate terminals, run the app on the host:
uvicorn backend_api:app --reload --port 8000     # or: scripts/start-backend.ps1
cd frontend && npm run dev                        # or: scripts/start-frontend.ps1
```

The host backend reads `.env` automatically. Make sure it contains
`LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY=…`, and `DB_HOST=localhost`.
See [`docker-compose.override.yml.example`](docker-compose.override.yml.example)
for the full explanation of what the override does.

## Deploying to production

Production is the Docker stack deployed with the production env. There is no app
store — "releasing" means deploying the stack.

```bash
# 1. Configure production secrets (never commit this file)
cp .env.production.example .env.production
#    edit .env.production: POSTGRES_PASSWORD, ANTHROPIC_API_KEY,
#    BACKEND_API_SECRET, Google OAuth, etc.

# 2. Deploy
./deploy-production.sh               # Linux / CI
#  .\deploy-production.ps1           # Windows (PowerShell)
```

The deploy script validates `.env.production`, then brings up the stack via
`docker-compose` with the production environment. Full procedure and rollback
notes are in [`docs/DOCKER_DEPLOYMENT.md`](docs/DOCKER_DEPLOYMENT.md) and
[`docs/PRODUCTION_QUICK_START.md`](docs/PRODUCTION_QUICK_START.md).

## Project Structure

```
big-flavor-band-agent/
├── backend_api.py               # FastAPI app (entry point, mounted into Docker)
├── docker-compose.yml           # Service definitions
├── docker-compose.override.yml.example  # Host-dev override (copy to enable)
├── deploy-production.sh / .ps1   # Production deploy
├── src/
│   ├── agent/big_flavor_agent.py # Claude AI agent
│   ├── rag/                      # RAG semantic search
│   ├── mcp/                      # Audio production MCP server
│   └── llm/llm_provider.py       # Anthropic / Ollama provider abstraction
├── database/                     # DB manager + SQL schemas/migrations
├── frontend/                     # Next.js web app
├── streaming/                    # Icecast + Liquidsoap radio config
├── scripts/                      # Helper & one-off scripts (see scripts/README.md)
├── audio_library/                # Audio files (indexed)
├── docs/                         # Documentation
└── tests/                        # pytest suite
```

See [`scripts/README.md`](scripts/README.md) for what each helper script does.

## Features

### Search Tools (RAG System)
- 🎵 **Audio Similarity** - Find songs that sound similar
- 📝 **Text Search** - Natural language queries
- 🎼 **Tempo Search** - Find songs by BPM
- 🔀 **Hybrid Search** - Combine multiple criteria

### Production Tools (MCP Server)
- 🔍 **Analyze Audio** - Extract tempo, key, beats
- ⏱️ **Match Tempo** - Time-stretch without pitch change
- 🎚️ **Create Transitions** - Beat-matched DJ mixes
- 🎛️ **Apply Mastering** - Professional audio mastering

## Usage Examples

```python
# Search for similar songs
"Find songs that sound like my-track.mp3"

# Natural language search
"Find calm ambient sleep music"

# Tempo-based search
"Find songs between 120-130 BPM"

# Audio production
"Analyze the tempo of song.mp3"
"Make this song 128 BPM"
"Create a DJ transition from song1.mp3 to song2.mp3"
```

## Development

### Running Tests

The test suite lives under `tests/` and runs with `pytest`:

```bash
pytest                      # run the whole suite
pytest tests/test_rag.py    # a single file
```

Interactive agent runners (handy for manual debugging) live in `scripts/` —
e.g. `python scripts/run_agent.py`. See [`scripts/README.md`](scripts/README.md).

### Adding New Search Methods

Edit `src/rag/big_flavor_rag.py` and add methods to `SongRAGSystem` class.

### Adding New Production Tools

Edit `src/mcp/big_flavor_mcp.py` and add tools to `BigFlavorMCPServer` class.

## Documentation

See `docs/` directory for detailed documentation:
- `SIMPLIFIED_ARCHITECTURE.md` - Architecture overview
- `TOOL_ROUTING_GUIDE.md` - Tool usage guide
- Setup guides and more

## Requirements

- Python 3.8+
- PostgreSQL with pgvector extension
- Anthropic API key
- ~2GB disk space for audio library

## License

See LICENSE file for details.

## Support

For issues or questions, see documentation in `docs/` directory.

---

**Note**: This is a refactored, clean architecture with proper separation of concerns:
- Search operations use RAG system library directly (fast!)
- Production operations use MCP server (isolated process)
- Agent orchestrates both seamlessly
