# Architecture — Big Flavor Band Agent

This document captures significant architectural decisions and patterns. Update it when making
decisions that are not obvious from reading the code.

---

## High-Level Structure

An AI music assistant over the Big Flavor Band catalog. A Next.js frontend talks to a FastAPI
backend, which orchestrates an LLM agent, a RAG search system, and a production MCP server over a
PostgreSQL/pgvector database. A separate Icecast + Liquidsoap pair provides the live radio stream.

```mermaid
flowchart TD
    frontend["Next.js frontend/<br/>(app router)"]

    subgraph backend["FastAPI backend (backend_api.py)"]
        agent["BigFlavorAgent<br/>src/agent/"]
        rag["SongRAGSystem<br/>src/rag/ (search)"]
        mcp["Production MCP<br/>src/production/"]
        db["DatabaseManager<br/>database/"]
    end

    radio["Icecast + Liquidsoap<br/>(radio)"]
    postgres[("PostgreSQL + pgvector<br/>(songs, lyrics, embeds)")]

    frontend -->|"HTTP /api/*"| backend
    backend -->|stream| frontend
    frontend -->|"&lt;audio&gt; /stream"| radio
    backend -->|"playlist .m3u"| radio

    agent -->|tool calls| mcp
    rag -->|pgvector| db
    db --> postgres
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
  production/
    big_flavor_mcp.py         # MCP server host — advertises + dispatches the tool registry
    toolkit.py                # AudioTool base, Param schema, ToolContext, REGISTRY, @register
    audio_io.py               # shared load/write/per-channel helpers + WAV subtypes
    analysis.py               # shared DSP analysis (key/beat/pitch/hum/LUFS + per-tool loaders)
    region.py                 # region scoping (resolve_region/apply_to_region/blend_strength)
    tools/                    # ONE FILE PER TOOL (trim_silence.py, reduce_noise.py, apply_eq.py, …)
database/
  database.py                 # DatabaseManager (asyncpg) — the single DB access point
  apply_schema.py             # schema bootstrap
  sql/init/*.sql              # initial schema (songs, details, audio embeddings)
  sql/migrations/*.sql        # versioned migrations (song_id→int, users table)
frontend/
  app/                         # Next.js app-router pages + /api route handlers (BFF)
  components/                  # React components (AudioPlayer, SongList, SearchBar, …)
    produce/audio/              # Audio-processing review-queue UI (VersionBar, StemConsole,
                                 #   StemRow, StemDetailPanel, FixQueue/FixCard, AdvancedDrawer,
                                 #   ResultSidebar, LyricsCard, Spinner, useStemPlayback,
                                 #   fixCopy.ts, stemColors.ts)
  hooks/useProcessingQueue.ts  # Data-flow hub for the audio-processing review queue (analyze fan-out,
                                #   FixEntry state, accept/preview)
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
env var (`anthropic` | `ollama`); Ollama (qwen2.5:14b, GPU) is the default in `docker-compose.yml`
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

**Per-tool registry (2026-07):** each tool is a self-contained `AudioTool` subclass in its own file
under `src/production/tools/` (one file per tool — adding a tool = adding a file), registered into
`toolkit.REGISTRY` via `@register`. A tool declares `params` (a list of `Param` with
default/min/max/label/choices that renders as both a JSON inputSchema and a UI control) and implements
`analyze(ctx, …)` (inspect-only: returns `{recommended, params, findings, reason}`) and
`apply(ctx, …)` (the processing). `BigFlavorMCPServer` is a thin host: `list_tools()` and
`dispatch_tool()` are generic loops over the registry, `analyze_tool()` runs the read side, and a
`__getattr__` shim resolves `server.<tool>(…)` to the tool's `apply` (bound to a shared `ToolContext`)
so legacy positional-arg call sites and the auto-clean orchestrator keep working. Shared DSP lives in
`audio_io.py`/`analysis.py`, re-exported from `big_flavor_mcp` so older imports (e.g. `_detect_beats`
in `produce.py`) still resolve. The **per-tool HTTP surface** is `GET /api/produce/tools` +
`POST /api/produce/tools/{tool}/{analyze,apply}` (`src/api/routers/produce.py`), driving the produce
editor's **ToolPanel** (`frontend/components/produce/ToolPanel.tsx`): adjust a tool's params →
Analyze (see findings, optionally adopt suggested values) → Apply (saves a candidate version).

**Region scoping** (`src/production/region.py`): `resolve_region`/`apply_to_region` let a cleanup
tool (trim, hum, noise, EQ) confine itself to a `start_s`/`end_s` span, splicing the processed region
back in with a short crossfade so audio outside it is untouched (bit-identical). Normalize and
Master are **whole-track** operations (peak normalization / integrated LUFS) and never take a region.

**Unified analyze-and-clean pipeline** (`analyze_and_recommend_processing` → `auto_clean_recording`,
now registry tools in `tools/analyze_recommend.py` + `tools/auto_clean.py` — the latter orchestrates
the other tools via `REGISTRY`; reached over `src/api/routers/produce.py`'s `/api/produce/analyze` +
`/api/produce/auto-clean`): the `/produce`
editor's "Whole song" and "Region" selection modes both drive this one pipeline — a region is a scope
passed to `start_s`/`end_s`, not a different tool. Analysis returns a per-step
`recommended_intensity` (gentle/moderate/aggressive) derived from its own measurements (noise floor,
crest factor, EQ correction count); the UI pre-fills each step's raw parameters from that suggestion
and lets the user hand-tune any of them via `step_params` (e.g. `{"master": {"target_lufs": -12}}`),
which always wins over the `aggressiveness`-scaled recommendation. A region request forces
Normalize/Master off regardless of `steps_override`, and region-mode Trim routes through
`trim_silence`'s own scoped silence-trim (not the whole-file crop-to-detected-span path) so it can
never delete audio outside the selected span. Two further steps, `pitch` and `tempo`, are opt-in only
(no analysis measurement recommends either): `pitch` calls the existing `correct_pitch` tool
(auto-tune, key-aware) and is region-scoped like trim/noise/EQ; `tempo` calls the existing
`match_tempo` tool (whole-track time-stretch to an explicit target BPM) and is forced off under a
region exactly like Normalize/Master, since it has no region parameter (issue #82).

**Per-stem analyze/apply (2026-08):** `AudioTool.analyze()`/`apply()` were already file-path-agnostic
(they only ever see a `file_path`), so a separated stem's own audio is just another file to run a
tool against — no DSP changes were needed. `src/api/routers/produce.py`'s `ToolRunRequest` takes an
optional `stem_id`, resolved via `_resolve_tool_source_path` → `db.get_stem`/`db.get_stem_set` (404 on
song-ownership mismatch). A stem-scoped `apply` is always a preview render (no version write) — only
`POST /api/produce/accept-fixes` creates a version, by chain-applying each stem's accepted fixes
(`_chain_apply_tools`, step N's output feeding step N+1), remixing them at unity gain
(`stem_separation.remix_stems`), then chain-applying master-bucket fixes on the remix.
`POST /api/produce/stems/{stem_id}/preview-chain` renders one stem's enabled chain for audition only.
`AudioTool.confidence_tier(value, high, worth, higher_is_worse)` (`toolkit.py`) buckets a tool's own
measured magnitude into `"high"`/`"worth_a_listen"`/`None`, surfaced as `analyze()`'s `confidence` key
on the 7 tools with real measurements — the review-queue UI's per-card confidence tag.

**Full mix as a console row (2026-08):** the stem console's first row is a *pseudo-stem*
(`FULL_MIX_STEM_ID = -1` in `useProcessingQueue.ts`) whose fixes are the master-scoped ones, so the
whole song is played, analyzed and fixed through the same row UI as its parts. It exists only in the
frontend — the accept/apply payloads still carry real stem ids plus a `master_fixes` list, so no
backend code knows about it. It plays through the same mixer but starts **muted**: the stems already
sum to the mix, so an un-muted mix channel would double every part.

**Stem instrument tagging (2026-08):** Demucs' source list is fixed by the model weights
(`htdemucs_6s` = vocals/drums/bass/guitar/piano/other), so a banjo, mandolin or fiddle lands inside
`other` — present in the audio, but unnamed. Rather than separating instruments the model was never
trained on, `src/production/instrument_tagging.py` *labels* each stem with an AudioSet tagger
(`MIT/ast-finetuned-audioset-10-10-0.4593`, multi-label so one stem reports "banjo *and* fiddle"),
mapping AudioSet's comma-separated display names onto a curated producer-facing vocabulary. Scores
are taken as the **max** across evenly-spaced non-silent windows, not the mean — an instrument that
only plays one section must still be reported. An all-silent stem returns `silent: true`, which is a
real answer (a band with no piano still gets a piano stem). Tagging runs in `stem_jobs.py` *after*
the set is marked complete, best-effort: a tagging failure never fails a separation that produced
usable stems. `song_stems.display_name` lets a producer override the label by hand
(`PATCH /api/produce/stems/{id}`); `POST /api/produce/stems/{id}/identify` is the per-stem retry.
`name` always stays the Demucs source name, because that is what the fix tools resolve against.

---

## Frontend Theming

Dark-only "Console" design system (2026-08) — there is no light mode and no toggle:
`frontend/tailwind.config.ts` sets `darkMode: 'class'` and defines the token palette (`canvas/panel/
raised/well/signal/confirm/attention/text`, plus `stem.{vocals,drums,bass,other,guitar,piano}` accent
colors); `frontend/app/layout.tsx` loads IBM Plex Sans/Mono via `next/font/google` and applies a
permanent `className="dark"` to `<html>`. New components use the token utilities directly
(`bg-panel`, `text-text`); pages migrated before this token set existed still carry paired
`bg-white dark:bg-gray-800`-style Tailwind classes, which now render correctly since `darkMode:'class'`
+ the permanent `dark` class makes the `dark:` variant always win — a page can be migrated to the
token utilities at any time without breaking in the meantime.

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

Live radio is decoupled from the API. Runtime radio state (current song, queue, play/pause,
position) and the active-listener set are stored **process-externally in PostgreSQL** via
`RadioStateStore` (`database/radio_state_store.py`) — a single-row `radio_state` JSONB table plus a
`radio_listeners` table (migration `06`). The radio endpoints load the state, mutate it, and save it
back on each request, so state survives a backend restart and stays consistent across backend
instances (issue #2). The backend still writes `streaming/playlist/radio.m3u` from that state;
Liquidsoap reads the shared file and streams to Icecast, proxied by nginx at `/stream`. Two
invariants the code depends on (regressions here silently break the stream):
- Liquidsoap playlist sources must be wrapped in `mksafe()` or `fallback` chooses `blank()`.
- Playlist paths are rewritten `/app/audio_library/…` → `/audio_library/…` to match Liquidsoap's
  mount (`write_playlist_file()` in `backend_api.py`).

See `AGENTS.md` → "Radio Streaming Architecture" for the operational details.

---

## Authentication

Google OAuth (Auth0-style) via NextAuth in the frontend (`app/api/auth/[...google]`), supporting
**multiple callback URLs** so the same config works in dev and prod (commit `6718150`). User
records + roles live in Postgres (migration `05`); admin role management is gated through
`/api/admin/*`. Setup is documented in `docs/GOOGLE_OAUTH_SETUP_GUIDE.md`.

---

## Deployment

Docker Compose, 7 services (see the table in `AGENTS.md`). Production support (`docker-compose`
prod env, nginx SSL, `deploy-production.{sh,ps1}`) was added in commit `c633d34`; SSL handling
refined in `00a73fa`. Details in `docs/DOCKER_DEPLOYMENT.md` / `docs/PRODUCTION_QUICK_START.md`.

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
| 2026-07 | Per-tool audio registry: one file per tool + `analyze`/`apply` contract | The 3,900-line MCP monolith made adding a tool a 3-place edit and the analyze step all-or-nothing. Every tool — single effects *and* the whole-song `analyze_and_recommend_processing`/`auto_clean_recording` orchestrators — is now a self-contained `AudioTool` under `tools/` with declared params; the server dropped to ~190 lines as a generic host over `REGISTRY` (no audio logic). New `/api/produce/tools/{tool}/{analyze,apply}` surface + ToolPanel give a per-tool "adjust params → analyze → apply" flow; the whole-song one-click clean is preserved, now registry-backed. `region_tools.py`'s param whitelist is derived from the registry. |
| 2025-12 | Frontend shows raw results, not the agent's prose (`eb3a032`) | Surfacing structured search results is clearer for music discovery than an LLM narration. |
| 2026-06 | Radio state externalized to PostgreSQL via `RadioStateStore` (migration `06`, issue #2) | In-memory per-process radio state was wiped on every backend restart and diverged across replicas; backing it with Postgres (no new infra) makes the radio restart-tolerant and stateless (OKR O3.3 / O4.3). |
| 2026-07 | `/produce`'s Region mode reuses the whole-song analyze-and-clean pipeline instead of a separate single-tool flow (issue #77 follow-up) | A region is just a scope (`start_s`/`end_s`), not a different tool — users expect the same "detected issues → tunable steps" experience either way. Region-mode Trim goes through `trim_silence`'s own scoped silence-trim, not the whole-file crop-to-detected-span path, so a mid-track selection can never delete audio outside it. |
| 2026-07 | Per-step `step_params` override wins over `aggressiveness`-scaled recommendations, not a per-step multiplier (issue #77 follow-up) | Keeps one resolution rule (explicit value → else `aggressiveness`-scaled recommendation → else default) instead of the backend tracking five independent intensity dials; the per-step Intensity presets in the UI are computed client-side with the same multiplier formula and sent as explicit overrides. |
| 2026-07 | Pitch correction and Tempo/beat correction restored as opt-in steps inside `auto_clean_recording`, not a separate tool/UI path (issue #82) | PR #81's per-step rework dropped both from the `/produce` UI. Rather than resurrect the old standalone region-tool flow, they're added as two more steps in the one unified pipeline, each with its own controls (no shared Intensity) since no analysis measurement backs either — `pitch` (`correct_pitch`, region-scoped) and `tempo` (`match_tempo`, whole-track only, forced off under a region like Normalize/Master). |
| 2026-07 | Agent pipeline made concurrency-safe + runnable in GitHub Actions (`.github/workflows/fix-issue.yml`) | Ported soccer-assistant-coach's standards: AGENTS.md Concurrency rules (re-check before write; races are benign; dev claims via `dev-agent:claim`; never touch dirty human trees) so local scheduled, interactive, and CI sweeps can overlap safely. CI sweeps trigger on human activity only (marker-filtered `issue_comment`), agents detect CI via `$GITHUB_ACTIONS` and honestly skip Docker-dependent checks. |
| 2026-08 | Dark-only "Console" design system, no light/dark toggle | The source design (a Claude Design mockup) had zero light-mode artifacts and stated "dark because you stare at waveforms"; building a toggle would have been speculative scope nobody asked for. `darkMode:'class'` + a permanent `dark` class on `<html>` also made every pre-existing `dark:` Tailwind class elsewhere in the app activate unconditionally for free, so unmigrated pages don't look broken in the meantime. |
| 2026-08 | Retired `MultitrackEditor.tsx`/`StemMixer.tsx` for a new `produce/audio/` component tree, not an in-place rewrite | The review-queue interaction model (analyze once → one card per fix → accept all) is different enough from the old per-tool-checkbox model that patching in place would have compounded an already-1319-line file. Only the genuinely reusable pieces (the Web Audio group-playback engine, the waveform canvas + region drag-select) were extracted into shared hooks/props instead of duplicated. |
| 2026-08 | Stem-scoped `apply` never writes a version; only `/api/produce/accept-fixes` does | Keeps "create a version" a single seam. Per-stem/per-fix "Hear it" and "Preview with fixes" auditioning needed to be cheap and side-effect-free, so every per-tool or per-stem render is a preview; only the explicit accept-fixes orchestrator (which composes every stem + master fix into one file) is allowed to call `save_candidate_version`. |
| 2026-08 | Tag instruments on stems instead of trying to separate more of them | Demucs' source list is baked into the model weights, so "add banjo/mandolin" is not a config change — it needs either query-based separation (materially worse quality than Demucs on its native sources) or a fine-tune on isolated multitracks the band doesn't have. But nothing is actually *lost*: the 6 stems sum back to the mix, so a banjo is present, just inside `other`. The gap is naming, not coverage — so an AudioSet tagger names what's in each stem and the producer can override the label by hand. Query-based separation stays on the table if per-instrument isolation later proves worth it. |
| 2026-08 | Instrument tagging runs after the stem set is marked `complete`, not before | Separation already takes minutes; making the producer wait on a second model pass before any waveform appears would compound the exact slowness the console was being fixed for. Tags are a labelling pass over stems that already exist, so the console renders immediately and the labels fill in behind via a bounded poll. It also means a tagging failure can't fail a separation that produced perfectly usable stems. |
