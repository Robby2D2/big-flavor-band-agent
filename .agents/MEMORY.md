# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> This memory was **reconstructed from git history** on 2026-06-19 (43 commits, 2025-11-05 →
> 2025-11-24, branch `front_end`). Dates below are the commit dates of the work described.

---

### 2026-07-13 — Release `v0.13.0` (release-manager)
Cut **`v0.13.0`** from `main` (HEAD `0a5c9fb`), a **minor** bump from `v0.12.0` — the 12-commit range
(5 merged feature PRs, #60–#64) is a run of production-pipeline `feat:` commits: preserve stereo
channels through all production tools, source noise profile from quietest frames + smooth the gate +
make high-pass opt-in, detect and remove mains hum (50/60 Hz + harmonics), preserve float precision
through the auto-clean chain and master at 24-bit, and apply all recommended EQ bands with true
peaking filters and measured LUFS mastering — plus the v0.12.0 memory chore and a `.gitignore` fix for
`.serena/` that had tripped the release-manager's dirty-tree guard on the prior run. Published GitHub
Release with auto-generated notes anchored to `v0.12.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.13.0. Notified linked closed issues
#55–#59. Sanity gate: backend restart **failed** again with the same pre-existing
`asyncpg.exceptions.DatatypeMismatchError` in `ensure_song_versions_table()` (local Postgres
`songs.id` is `character varying` vs. the integer FK the code expects) — confirmed via `git diff
v0.12.0..HEAD --stat` that this range touches only `src/agent/big_flavor_agent.py`,
`src/production/big_flavor_mcp.py`, tests, and non-code files, not `database/database.py` or
`backend_api.py`, so this is the same local DB-state drift noted in the v0.12.0/v0.7.0 entries, not a
regression. Frontend `npm run build` **passed**. Proceeded per Step 4.5.

### 2026-07-13 — Release `v0.12.0` (release-manager)
Cut **`v0.12.0`** from `main` (HEAD `d225259`), a **minor** bump from `v0.11.1` — the 3-commit range
includes a `feat:` commit (`bdd5aa2`, port concurrency standards from soccer-assistant-coach + run the
pipeline in GitHub Actions), plus a `fix:` (`d225259`, document `gh` self-approval restriction as
benign in qa-reviewer) and the v0.11.1 memory chore (`9abe59d`). All three commits touch only
`.agents/`, `.claude/agents/`, `AGENTS.md`, and `.github/workflows/` — no application/database code —
and were pushed directly to `main` without a PR, so there were no linked issues to notify. Published
GitHub Release with auto-generated notes anchored to `v0.11.1`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.12.0. Sanity gate: backend restart
**failed** with `asyncpg.exceptions.DatatypeMismatchError` in `ensure_song_versions_table()` (local
Postgres `songs.id` is `character varying`, incompatible with the FK the code expects) — confirmed
this is pre-existing local DB schema drift unrelated to the release range (no commit in range touches
`database/database.py` or `backend_api.py`), not a regression, so **not** treated as a blocking `main`
error. Frontend `npm run build` **passed**. Proceeded per Step 4.5.

### 2026-07-12 — Pipeline concurrency standards ported from soccer-assistant-coach + GitHub Actions sweep
Copied the sibling repo's updated agent standards. **AGENTS.md** gained a **Concurrency** section
(4 rules: re-check before write; lost races are benign skips, not errors; writers claim / readers
re-check; never touch a dirty human working tree) and now documents **two run environments** —
local Windows and headless GitHub Actions (`$GITHUB_ACTIONS` = `true`; no Docker stack in CI, so
agents run targeted pytest + frontend lint/build and honestly report what wasn't verified).
Agent-file changes: **developer** got a Step 3.5 `dev-agent:claim` protocol (claim comment →
sleep 5 → oldest active claim < 60 min wins), a dirty-tree/branch-exists guard before branching,
and a pre-push PR re-check (rejected feature-branch push = benign race); **cpo/pm/qa** re-fetch
markers immediately before posting; **release-manager** got a dirty-tree guard, a last-moment tag
idempotency re-check, and benign handling for tag-push races. Orchestrator gained a
**DEV-CLAIMED** triage bucket. New **`.github/workflows/fix-issue.yml`** runs the whole sweep via
`anthropics/claude-code-action@v1.0.140` on issue-opened/reopened + human (non-`-agent:`-marker)
comments + manual dispatch, replicating the local non-LLM gate; needs `BOT_TOKEN` and
`CLAUDE_CODE_OAUTH_TOKEN` secrets. Deliberately NOT ported: soccer's `pr-reviewer` split and
`COMPONENTS.md` (they exist there because its QA gate is an expensive cloud emulator run; QA here
is cheap/local).

### 2026-06-28 — Release `v0.11.1` (release-manager)
Cut **`v0.11.1`** from `main` (HEAD `bcc5121`), a **patch** bump from `v0.11.0` — the single commit in
the range is `bcc5121` (`chore: record v0.11.0 release in agent memory`), the release-manager's own
memory chore from the v0.11.0 cut. No `feat:`/`fix:`/`enhancement` and no linked PR/issue, so no
product change and no issues to notify. Published GitHub Release with auto-generated notes anchored to
`v0.11.0`: https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.11.1. Sanity gate: Docker
daemon down locally (infra, not a `main` error) so backend-boot check skipped; frontend `npm run build`
**passed** (confirms `main` healthy; the chore doesn't touch the frontend). Proceeded per Step 4.5.

### 2026-06-27 — Release `v0.11.0` (release-manager)
Cut **`v0.11.0`** from `main` (HEAD `912dd0a`), a **minor** bump from `v0.10.0` because the 3-commit
range adds a clear feature: a `feat:` commit (`963b4dd`, back-fill null catalog metadata — genre,
duration, tempo) merged via PR #54. Range also includes the v0.10.0 release-memory chore (`6364589`)
and the merge commit. Published GitHub Release with auto-generated notes anchored to `v0.10.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.11.0. Notified linked closed issue
#52. Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot check skipped;
frontend `npm run build` **passed**. The feature is a backfill script + DB work (not exercised by the
frontend build), so it relies on the per-PR QA gate. Proceeded per Step 4.5.

### 2026-06-27 — Release `v0.10.0` (release-manager)
Cut **`v0.10.0`** from `main` (HEAD `21a3abf`), a **minor** bump from `v0.9.1` because the 9-commit
range adds clear features: a `feat:` commit (`059df70`, add a recorded-on Date column to the Produce
catalog table) merged via PR #53, plus the null-metadata back-fill/derivation work (back-fill script
for `songs.session`/`recorded_on`, `insert_song()` now persisting them, and LLM-based energy/mood
derivation for all 1341 songs). Published GitHub Release with auto-generated notes anchored to `v0.9.1`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.10.0. Notified linked closed issue
#51. Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot check skipped;
frontend `npm run build` **passed** and validated the changed `/produce` catalog page. Proceeded per
Step 4.5.

### 2026-06-27 — Back-fill + derive null song metadata
Eight `songs` columns were entirely null (`energy, mood, recording_date, audio_quality, rating,
session, uploaded_on, recorded_on`). Root cause: `insert_song()` (`database/database.py`) only ever
wrote a fixed column set and **omitted `session`/`recorded_on`**, so scraped values were dropped on
load; and the audio-analysis scripts only wrote "basic fields" (`tempo_bpm, key, duration_seconds`),
never `energy`/`mood`. The `audio_analysis` table is empty — librosa energy/valence were never
populated.
- **Back-fill:** new `scraper/backfill_session_recorded_on.py` reads the latest `scraped_songs_*.json`
  and fills `session` (663) + `recorded_on` (661) by id. Dry-run by default; `COALESCE`-based so it
  never clobbers existing values; parses scraped `M/D/YY` as 20YY. Runs from the host venv against
  the exposed DB (`localhost:5432`) — the `scraper/` dir is **not** mounted into `bigflavor-backend`.
- **Prevent recurrence:** `insert_song()` now persists `session`/`recorded_on` (new `_parse_recorded_on`
  helper coerces `M/D/YY`/ISO/`date` → DATE), with `COALESCE(EXCLUDED.…, songs.…)` on conflict so a
  re-scrape lacking a field won't wipe a back-filled value.
- **Derive energy/mood:** new `src/rag/derive_energy_mood.py` classifies all 1341 songs via
  `get_llm_provider()` (ran on Ollama `mistral-nemo`) from title/metadata/lyrics, constrained to a
  controlled vocab (`energy` low/medium/high; ~14 `mood` labels). CLI mirrors `index_lyrics`
  (`--status/--limit/--reindex/--dry-run`); **run inside `bigflavor-backend`** where LLM+DB env is
  wired. A single corrective retry handles out-of-vocab replies → **1341/1341** set. Distribution:
  energy mostly `medium` (703); mood dominated by `melancholic` (624). Merged to `main` via branch
  `fix/backfill-and-derive-song-metadata`.

### 2026-06-27 — Release `v0.9.1` (release-manager)
Cut **`v0.9.1`** from `main` (HEAD `f3dbcc5`), a **patch** bump from `v0.9.0` because the 4-commit
range has no new feature — the only product change is a `fix:` (`cd5cfb0`, replace the `/produce`
dropdown with a sortable catalog table + per-song detail page) merged via PR #50 (no `enhancement`
label). The other three commits are release-manager memory chores from the v0.9.0 cut (`eb848d3`,
`f3dbcc5`) and the merge commit (`fefb446`). Published GitHub Release with auto-generated notes anchored
to `v0.9.0`: https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.9.1. Notified linked
closed issue #49. Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot
check skipped; frontend `npm run build` **passed** and directly validated the changed `/produce` page
plus the new `/produce/[songId]` route. Proceeded per Step 4.5.

### 2026-06-27 — Release `v0.9.0` (release-manager)
Cut **`v0.9.0`** from `main` (HEAD `feee75c`), a **minor** bump from `v0.8.0` because the 6-commit
range includes a `feat:` commit (`1dfd759`, save auto-clean output as a candidate version on
`/produce`) merged via PR #48. Range also covers chores: local-dev against Anthropic + scripts/docs
reorg (`b295d6c`), node_modules gitignore + agent-memory update (`3328971`), and `cleanup` (`feee75c`).
Published GitHub Release with auto-generated notes anchored to `v0.8.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.9.0. Notified linked closed issue
#47. PR #50 was approved-but-unmerged and correctly **out of scope** for this release (per orchestrator
note). Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot check
skipped; frontend `npm run build` **passed**. Proceeded per Step 4.5.

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
