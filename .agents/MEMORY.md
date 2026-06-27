# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> This memory was **reconstructed from git history** on 2026-06-19 (43 commits, 2025-11-05 →
> 2025-11-24, branch `front_end`). Dates below are the commit dates of the work described.

---

### 2026-06-26 — Release `v0.8.0` (release-manager)
Cut **`v0.8.0`** from `main` (HEAD `2ed9f36`), a **minor** bump from `v0.7.0` because the 2-commit
range includes a `feat:` commit (`71bc42d`, manage song versions and set a default from `/produce`)
merged via PR #46. Published GitHub Release with auto-generated notes anchored to `v0.7.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.8.0. Notified linked closed issue
#43. Sanity gate: Docker daemon was down locally (infra, not a `main` error) so the backend-boot
check was skipped; frontend `npm run build` **passed** and directly validated the changed `/produce`
page plus the new version-management API routes (`/api/produce/versions/[versionId]/{audio,default,
rename}`). Proceeded per Step 4.5.

### 2026-06-23 — Release `v0.7.0` (release-manager)
Cut **`v0.7.0`** from `main` (HEAD `425091e`), a **minor** bump from `v0.6.0` because the 2-commit
range includes a `feat:` commit (`b3445e8`, inline help for the `/produce` configure-and-clean panel)
merged via PR #45. The only product change in the range is `frontend/app/produce/page.tsx`. Published
GitHub Release with auto-generated notes anchored to `v0.6.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.7.0. Notified linked closed issue
#44. Sanity gate: frontend `npm run build` **passed** (directly validates the changed page). Backend
boot **failed** with `asyncpg DatatypeMismatchError` on `song_versions_song_id_fkey` — local `songs.id`
is `varchar` but `ensure_song_versions_table` (database/database.py:294) declares `song_id INTEGER
REFERENCES songs(id)`. That code shipped in v0.6.0 (commit `6052d28`) and is **not** in this range, so
the failure is a local DB-state divergence (env), not a `main` error introduced here — noted and
proceeded per Step 4.5. Worth a human's eye if the local Postgres `songs.id` type ever needs
reconciling with the integer FK the code expects.

### 2026-06-22 — Release `v0.6.0` (release-manager)
Cut **`v0.6.0`** from `main` (HEAD `0ed449d`), a **minor** bump from `v0.5.0` because the 11-commit
range includes a `feat:` commit (`e970612`, clarify force-reclean has no effect) and merged feature
PR #41. Range covered the `/produce` analyze/auto-clean fixes (mcp dep, numpy JSON, writable produced
mount, before/after players), nginx path forwarding restore, and `AGENT_API_URL` next.config fallback.
Published GitHub Release with auto-generated notes anchored to `v0.5.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.6.0. Notified linked closed issues
#38 and #39. Sanity gate: Docker daemon was up but the full stack wasn't running (Postgres exited,
backend started clean with no logs) — treated as infra, not a `main` error, so proceeded.

### 2026-06-22 — `/produce` Analyze was a silent no-op: missing `mcp` dep + numpy JSON bug
`requirements-api.txt` never picked up the `mcp` package that
`src/production/big_flavor_mcp.py` needs (it's only listed in the older
`setup/requirements.txt`), so `BigFlavorMCPServer` failed to import and every
production tool call (`analyze_and_recommend_processing`, `auto_clean_recording`)
silently fell back to a generic `{"error": ..., "message": ...}` dict with no
`status` field — the `/produce` page couldn't tell it was an error and rendered an
empty "Detected issues" section instead. Fixed by adding `mcp>=1.0.0` to
`requirements-api.txt` and rebuilding the backend image (`baf940c`). Recreating
the backend container to pick up the new image also exposed that
`BACKEND_API_SECRET` was never persisted to `.env` (only set via an exported shell
var at the original `docker-compose up`), so every authenticated route 401'd
("Server auth is not configured") until it was added to `.env`. With the
dependency actually loaded, the real analysis code ran for the first time and hit
a third bug: three `"recommended"` flags were raw `numpy.bool_` values from numpy
comparisons, which FastAPI can't JSON-encode (500). Cast to `bool()`. Same day, a
separate fix (`2e76db0`, not from this session) repaired nginx's resolver-based
upstream variables, which had silently broken path forwarding (`/stream`,
`/icecast/`, the backend catch-all) and were missing frontend-BFF routes for
`/api/admin`, `/api/produce`, `/api/songs` — worth knowing if nginx 404s/502s show
up in this area again. **Lesson:** `requirements-api.txt` is maintained
separately from `setup/requirements.txt` and can silently drift; when a backend
tool "does nothing," check the startup log for "MCP production server loaded" vs
"not available" before chasing the data/network layer.

### 2026-06-20 — First tagged release `v0.1.0` (release-manager)
Adopted `vX.Y.Z` git-tag versioning. Cut the **first release `v0.1.0`** from `main` (HEAD `775e747`,
44 commits, no prior tag) and published a GitHub Release with auto-generated notes:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.1.0. No issues notified — the
initial history has no `#NN` PR references in commit subjects, so there were no linked closed issues.
Sanity gate skipped (Docker stack not running locally — infra, not a `main` error). The hygiene work
on `fix/container-config-hygiene-11` (`97c4eb6`) was **not** merged to `main` and is correctly out of
this release.

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

### 2026-06-20 — Radio state externalized to PostgreSQL (issue #2)
Runtime radio state (queue, now-playing, play/pause, position) and active listeners moved out of
per-process in-memory dicts in `backend_api.py` into a new `RadioStateStore`
(`database/radio_state_store.py`) backed by a single-row `radio_state` JSONB table + a
`radio_listeners` table (migration `06-create-radio-state-table.sql`). Endpoints now load → mutate →
save state per request, so the radio survives a backend restart and is consistent across instances.
Chose Postgres over Redis to avoid standing up new infra. Added `pytest`/`pytest-asyncio` dev deps,
a root `pytest.ini` (`asyncio_mode = auto`), and the first assert-based test
(`tests/test_radio_state_store.py`, fake DB pool — no live DB/LLM). Radio invariants preserved
(`mksafe()` sources untouched; `/app/audio_library` → `/audio_library` rewrite intact).

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
host. See `docs/DOCKER_DEPLOYMENT.md` / `docs/PRODUCTION_QUICK_START.md`.

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
- **Releases are git tags `vX.Y.Z` on `main`** (first: `v0.1.0`, 2026-06-20); patch-bump by default,
  minor-bump if the range adds a clear feature. No formal test suite yet — see [TESTING.md](TESTING.md).
