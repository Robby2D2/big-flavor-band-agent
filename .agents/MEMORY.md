# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> This memory was **reconstructed from git history** on 2026-06-19 (43 commits, 2025-11-05 →
> 2025-11-24, branch `front_end`). Dates below are the commit dates of the work described.

---

## Project snapshot (as of 2026-06-19)

AI music-discovery & production assistant over the Big Flavor Band catalog (~1,300 songs).
- **Backend:** FastAPI (`backend_api.py`) — search, agent/DJ, radio, tools, users/admin routes.
- **Frontend:** Next.js app-router (`frontend/`) with Google OAuth and an audio player.
- **Agent:** `src/agent/big_flavor_agent.py`, LLM-provider-agnostic (Ollama default / Claude).
- **Search:** `SongRAGSystem` (`src/rag/`) — text, lyric, audio-similarity, tempo, hybrid (pgvector).
- **Production:** MCP server (`src/production/big_flavor_mcp.py`) — analyze/tempo-match/transition/master.
- **Data:** PostgreSQL + pgvector; scraped from bigflavor.com; lyrics via Whisper large-v3.
- **Radio:** Icecast + Liquidsoap, playlist via shared `streaming/playlist/radio.m3u`.
- **Deploy:** Docker Compose (7 services); production env + nginx SSL.
- Active branch is `front_end`; `main` is the integration branch.

---

## Timeline (reconstructed from git)

### 2025-11-24 — Radio fixed (`60da3f0`)
Radio streaming stabilized. The key invariant: Liquidsoap playlist sources must be wrapped in
`mksafe()` or `fallback` chooses `blank()` (silence) even with valid playlists; and the backend must
rewrite playlist paths `/app/audio_library/…` → `/audio_library/…` to match Liquidsoap's mount. See
[memory/radio_streaming.md](memory/radio_streaming.md).

### 2025-11-23 — Frontend shows results, not agent prose (`eb3a032`)
Dropped the LLM narration from the UI and display raw structured search results — clearer for music
discovery.

### 2025-11-21 — Search improvements (`c41f90c`)
Iterated on search relevance/behavior.

### 2025-11-19 → 11-20 — Production deployment support (`c633d34`, `00a73fa`)
Added a production Docker environment and nginx SSL handling, making the stack deployable to a real
host. See `DOCKER_DEPLOYMENT.md` / `PRODUCTION_QUICK_START.md`.

### 2025-11-15 — Auth: Google OAuth multi-URL (`6718150`)
Auth0/Google OAuth updated to support multiple callback URLs so one config works in dev **and** prod.
Users/roles live in Postgres (migration `05`); admin routes under `/api/admin/*`.

### 2025-11-11 → 11-12 — Frontend first pass (`5a9bffa`, `2f814e2`)
Initial Next.js frontend built and stabilized (search UI, audio player, components).

### 2025-11-10 — Full lyric + semantic search (`3a4145c`)
Lyric search combines full-text and semantic (embedding) matching.

### 2025-11-09 — Scraper indexes audio + all songs, incremental mode (`eb66637`, `0088ee6`, `3380d15`)
Scraper extended to index audio embeddings as well as metadata, to cover the whole catalog, and to
**process only missing data** on re-runs (idempotent ingest).

### 2025-11-08 — Whisper large-v3 for lyric transcription (`09bb7ba`, `ef42485`, `8fae495`)
Upgraded the lyric transcription model to Whisper large-v3 for accuracy; added GPU testing tools.

### 2025-11-07 — Editing, title similarity, lyric matching, RAG/MCP split hardened
(`a26b484`, `ce6d272`, `9becb30`, `96ce1b5`, `f8ac5a0`, `cb57406`, `72d7816`, `36e8f74`, `74ceb66`)
Song editing added; title-similarity and lyric matching search; tool calling fixed; the READ (RAG
library) vs WRITE (MCP server) separation cleaned up and the directory structure reorganized.

### 2025-11-07 — DB credentials moved to `.env` (`caf28a0`)
Stopped committing DB creds; `DatabaseManager` now reads `DB_*` / `DATABASE_URL` from env.

### 2025-11-06 — Core system built: Postgres, scraper, RAG, MCP, agent
(`98137ed`, `c52897d`…`dfe659c`, `41180f4`, `cd8f253`, `972aea3`, `7dff5a1`)
Stood up PostgreSQL, screen-scraped the catalog (with de-duplication), created the RAG search system,
wired RAG into the MCP server, and added the AI agent — the first end-to-end agent/MCP/RAG pass.

### 2025-11-05 — Project genesis (`410268b`, `9e57cb4`, `fa83538`)
Initial commit, first generation of the system, RSS feed for the MCP server. (An early TypeScript
version, `15b3901`, was superseded by the Python implementation.)

---

## Standing facts worth keeping in working memory

- **LLM calls go through `src/llm/llm_provider.py`** — never `import anthropic` in agent logic. Switch
  Ollama↔Anthropic via the `LLM_PROVIDER` env var.
- **DB access goes through `DatabaseManager`** (`database/database.py`, asyncpg); creds from env.
- **READ = RAG library (in-process), WRITE = MCP server (separate process).** Don't blur them.
- **Radio invariants:** `mksafe()`-wrapped Liquidsoap sources + the `/app/audio_library` →
  `/audio_library` playlist path rewrite. Regressing either causes silent dead air.
- **Hot reload:** restart `bigflavor-backend`, don't rebuild (source is volume-mounted). Liquidsoap
  config changes need a **no-cache** rebuild.
- **Schema changes are migrations** under `database/sql/migrations/`, not edits to `init/*.sql`.
- No git tags / no formal test suite yet — see [TESTING.md](TESTING.md).
