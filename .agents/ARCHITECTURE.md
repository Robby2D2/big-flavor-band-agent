# Architecture — Big Flavor Band Agent

This document captures significant architectural decisions and patterns. Update it when making
decisions that are not obvious from reading the code.

---

## High-Level Structure

An AI music assistant over the Big Flavor Band catalog. A Next.js frontend talks to a FastAPI
backend, which orchestrates an LLM agent, a RAG search system, and a production MCP server over a
PostgreSQL/pgvector database. A separate Icecast + Liquidsoap pair provides the live radio stream.

```
┌──────────────┐   HTTP    ┌─────────────────────────────────────────────┐
│  Next.js     │──────────▶│  FastAPI backend  (backend_api.py)          │
│  frontend/   │  /api/*    │  ┌───────────────┐  ┌────────────────────┐ │
│  (app router)│◀──────────│  │ BigFlavorAgent │  │ SongRAGSystem      │ │
└──────┬───────┘  stream   │  │ src/agent/     │  │ src/rag/  (search) │ │
       │                   │  └──────┬────────┘   └─────────┬──────────┘ │
       │ <audio>/stream    │         │ tool calls           │ pgvector   │
       ▼                   │  ┌──────▼─────────┐   ┌─────────▼──────────┐ │
┌──────────────┐           │  │ Production MCP │   │ DatabaseManager    │ │
│ Icecast +    │◀──────────│  │ src/production/│   │ database/          │ │
│ Liquidsoap   │  playlist │  └────────────────┘   └─────────┬──────────┘ │
│ (radio)      │   .m3u    └────────────────────────────────┬┘            │
└──────────────┘                                            ▼             │
                                              ┌─────────────────────────┐ │
                                              │ PostgreSQL + pgvector    │◀┘
                                              │ (songs, lyrics, embeds)  │
                                              └─────────────────────────┘
```

### Directory layout

```
backend_api.py            # FastAPI app — all HTTP routes, radio state, playlist writer
src/
  agent/big_flavor_agent.py   # LLM orchestration (Claude/Ollama) with tool calling
  rag/
    big_flavor_rag.py         # SongRAGSystem — semantic / text / lyric / hybrid search
    audio_embedding_extractor.py  # CLAP + librosa audio embeddings
    lyrics_extractor.py       # Whisper lyric transcription
    index_lyrics.py           # batch lyric indexing
  llm/llm_provider.py         # LLMProvider abstraction (AnthropicProvider, OllamaProvider)
  production/big_flavor_mcp.py # MCP server — audio production / write tools
database/
  database.py                 # DatabaseManager (asyncpg) — the single DB access point
  apply_schema.py             # schema bootstrap
  sql/init/*.sql              # initial schema (songs, details, audio embeddings)
  sql/migrations/*.sql        # versioned migrations (song_id→int, users table)
frontend/
  app/                        # Next.js app-router pages + /api route handlers (BFF)
  components/                 # React components (AudioPlayer, SongList, SearchBar, …)
streaming/
  radio.liq                   # Liquidsoap config
  playlist/radio.m3u          # generated playlist (shared volume backend↔liquidsoap)
scraper/                      # one-off catalog scrapers (bigflavor.com → DB)
tests/                        # ad-hoc Python test/demo scripts (see TESTING.md)
docker-compose.yml            # 7-service stack
```

---

## Backend (FastAPI)

`backend_api.py` is the single HTTP surface. It owns three long-lived singletons initialised at
startup: `agent` (`BigFlavorAgent`), `rag` (`SongRAGSystem`), and `db_manager` (`DatabaseManager`).

Route groups (see the `@app.*` decorators):
- **Users / admin** — `/api/users`, `/api/admin/users`, role management (backed by the users table
  from migration `05`).
- **Search** — `/api/search/natural`, `/api/search/text`, `/api/search/lyrics`,
  `/api/songs/{id}/lyrics`. These call the RAG system directly (fast path, no LLM round-trip).
- **Agent / DJ** — `/api/agent/chat` (streaming), `/api/agent/dj/request`, `/api/agent/dj/playlist`.
  These go through `BigFlavorAgent` for LLM reasoning + tool calls.
- **Radio** — `/api/radio/state`, `/api/radio/queue/add|remove`, `/skip`, `/play`, `/pause`, plus the
  `/stream`, `/stream.m3u`, `/api/audio/stream/{id}` endpoints.
- **Tools** — `/api/tools/list`, `/api/tools/execute` (exposes the production/MCP tools).

The frontend never calls the backend directly from the browser for protected actions — it proxies
through Next.js `app/api/*` route handlers (a BFF layer that injects auth).

---

## LLM Provider Abstraction

`src/llm/llm_provider.py` defines `LLMProvider` (ABC) with `AnthropicProvider` and `OllamaProvider`
implementations and a `get_llm_provider()` factory. The provider is selected by the `LLM_PROVIDER`
env var (`anthropic` | `ollama`); Ollama (qwen2.5:7b, GPU) is the default in `docker-compose.yml`
for cost-free local inference, with Anthropic Claude as the hosted option. **All agent code goes
through this abstraction — never import `anthropic` directly in agent logic.** Both providers
implement `generate_with_tools()` so tool calling works regardless of backend.

---

## Search & RAG

`SongRAGSystem` (`src/rag/big_flavor_rag.py`) is the read/search path and is called **directly** by
the backend (it is a library, not a service) for speed. It combines:
- **Audio embeddings** — CLAP + librosa features (`audio_embedding_extractor.py`), stored as pgvector.
- **Text/metadata embeddings** — `sentence-transformers`.
- **Lyrics** — Whisper-transcribed (`lyrics_extractor.py`, large-v3 model), indexed for full-text +
  semantic lyric search.

Search modes: audio similarity, natural-language/text, lyric, tempo (BPM), and hybrid. `pgvector`
provides the vector similarity; SQL search functions live in `database/sql/` and
`database/update_search_functions.sql`.

> **Design split (KISS/SRP):** READ/search = RAG library (in-process, fast). WRITE/production =
> MCP server (`src/production/big_flavor_mcp.py`, isolated process). The agent orchestrates both.

---

## Production MCP Server

`src/production/big_flavor_mcp.py` (`BigFlavorMCPServer`) exposes audio-production/write tools over
the Model Context Protocol (analyze tempo/key/beats via librosa, tempo-match/time-stretch,
beat-matched transitions, mastering). It runs as a separate process so heavy audio work is isolated
from the API event loop.

---

## Database

- **Engine:** PostgreSQL with the **pgvector** extension (`ankane/pgvector` image).
- **Access:** a single `DatabaseManager` (`database/database.py`, asyncpg). All DB access goes
  through it — credentials come from `DB_*` / `DATABASE_URL` env vars (never hardcoded; moved to
  `.env` in commit `caf28a0`).
- **Schema:** `database/sql/init/*.sql` for the base schema (songs → details → audio embeddings),
  `database/sql/migrations/*.sql` for changes. `song_id` was migrated from string to integer
  (migration `04`); a users table was added for auth/roles (migration `05`).
- Apply schema with `database/apply_schema.py`; run migrations with `database/run_migration.py`.

---

## Radio Streaming (Icecast + Liquidsoap)

Live radio is decoupled from the API. The backend maintains `radio_state` (current song, queue,
play/pause, position) in-process and writes `streaming/playlist/radio.m3u`; Liquidsoap reads that
shared file and streams to Icecast, proxied by nginx at `/stream`. Two invariants the code depends
on (regressions here silently break the stream):
- Liquidsoap playlist sources must be wrapped in `mksafe()` or `fallback` chooses `blank()`.
- Playlist paths are rewritten `/app/audio_library/…` → `/audio_library/…` to match Liquidsoap's
  mount (`write_playlist_file()` in `backend_api.py`).

See `AGENTS.md` → "Radio Streaming Architecture" for the operational details.

---

## Authentication

Google OAuth (Auth0-style) via NextAuth in the frontend (`app/api/auth/[...google]`), supporting
**multiple callback URLs** so the same config works in dev and prod (commit `6718150`). User
records + roles live in Postgres (migration `05`); admin role management is gated through
`/api/admin/*`. Setup is documented in `GOOGLE_OAUTH_SETUP_GUIDE.md`.

---

## Deployment

Docker Compose, 7 services (see the table in `AGENTS.md`). Production support (`docker-compose`
prod env, nginx SSL, `deploy-production.{sh,ps1}`) was added in commit `c633d34`; SSL handling
refined in `00a73fa`. Details in `DOCKER_DEPLOYMENT.md` / `PRODUCTION_QUICK_START.md`.

---

## Significant Decisions Log

| Date | Decision | Rationale |
|---|---|---|
| 2025-11 | Split READ (RAG library) from WRITE (MCP server) | Search must be fast/in-process; production is heavy and benefits from process isolation. The agent orchestrates both. |
| 2025-11 | `LLMProvider` abstraction (Anthropic + Ollama) | Run a free local model (Ollama/qwen2.5) by default, switch to hosted Claude via one env var — without touching agent logic. |
| 2025-11 | DB credentials moved to `.env` (`caf28a0`) | Stop committing secrets; single `DatabaseManager` reads `DB_*`/`DATABASE_URL`. |
| 2025-11 | `song_id` migrated string→integer (migration `04`) | Stable integer keys for joins, embeddings, and audio-file matching (`{song_id}_*.mp3`). |
| 2025-11 | Whisper large-v3 for lyric transcription (`09bb7ba`) | Higher transcription accuracy enabled reliable full-lyric + semantic lyric search. |
| 2025-11 | Radio = Icecast + Liquidsoap, playlist via shared `.m3u` | Decouple continuous streaming from the request/response API; backend only writes queue state. |
| 2025-11 | `mksafe()` wrapper on Liquidsoap sources | Without it `fallback` picks `blank()` even with valid playlists (sources look "not ready" at init). |
| 2025-12 | Auth0/Google OAuth with multiple callback URLs (`6718150`) | One OAuth app serves both dev and prod redirect URLs. |
| 2025-12 | Production Docker environment + nginx SSL (`c633d34`, `00a73fa`) | Make the stack deployable to a real host, not just localhost. |
| 2025-12 | Frontend shows raw results, not the agent's prose (`eb3a032`) | Surfacing structured search results is clearer for music discovery than an LLM narration. |
