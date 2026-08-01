# Release History — Big Flavor Band Agent

Rolling, dated record of every `vX.Y.Z` release cut by the release-manager agent. Moved out of
`MEMORY.md` during a 2026-08-01 prune (routine/repetitive entries, low ongoing signal once a release
is out). Newest at top.

---

### 2026-07-31 — Release `v0.16.2` (release-manager)
Cut **`v0.16.2`** from `main` (HEAD `b8894a1`), a **patch** bump from `v0.16.1` — the 3-commit range
has no new feature: it's a docs-only change (`ddb2f82`, convert ASCII architecture diagrams to
Mermaid) merged via a direct merge commit (`b8894a1`, no PR reference), plus the v0.16.1 memory
chore (`07fc8d6`). No `#NN` PR references in the commit subjects, so no linked closed issues to
notify. Published GitHub Release with auto-generated notes anchored to `v0.16.1`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.16.2. Sanity gate: Docker was up;
backend restart booted clean (RAG system ready, MCP production server loaded, DB pool created,
CLAP model warm-up hit HF as expected on cold start) — the only log error was the same pre-existing
`PermissionError` on `/app/streaming/playlist/radio.m3u` in the radio loop noted since v0.14.0
(local volume-mount permission issue, unrelated to this docs-only range). Frontend `npm run build`
**passed**. Proceeded per Step 4.5.

### 2026-07-30 — Release `v0.16.1` (release-manager)
Cut **`v0.16.1`** from `main` (HEAD `adefdb8`), a **patch** bump from `v0.16.0` — the 3-commit range
has no new feature: the only product change is a `fix:` (`8f62529`, keep radio Now Playing/Up Next in
sync with the live stream) merged via PR #80, plus its merge commit and the v0.16.0 memory chore
(`ed4698a`). Published GitHub Release with auto-generated notes anchored to `v0.16.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.16.1. Notified linked closed issue
#79. Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot check
skipped; frontend `npm run build` **passed** and built the radio routes (`/radio`, `/api/radio/*`)
this fix touches. Proceeded per Step 4.5. (Note: a stray untracked `err.txt` sat at repo root — not
tracked human work, left untouched.)

### 2026-07-30 — Release `v0.16.0` (release-manager)
Cut **`v0.16.0`** from `main` (HEAD `d99b4e0`), a **minor** bump from `v0.15.0` — the 4-commit range
includes a `feat:` commit (`8c6c128`, unify analyze/clean and the waveform editor into one `/produce`
panel) merged via PR #78, plus a waveforms follow-up (`d99b4e0`) and the v0.15.0 memory chore
(`a59554f`). Published GitHub Release with auto-generated notes anchored to `v0.15.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.16.0. Notified linked closed issue
#77. Sanity gate: Docker daemon down locally (infra, not a `main` error) so backend-boot check
skipped; frontend `npm run build` **passed** and directly validated the changed `/produce` page.
Proceeded per Step 4.5.

### 2026-07-14 — Release `v0.15.0` (release-manager)
Cut **`v0.15.0`** from `main` (HEAD `8d59ce5`), a **minor** bump from `v0.14.0` — the 4-commit range
is a single merged PR (#76, closing issue #70): a `feat:` commit (`5c20f7c`, add a multitrack
producer UI with region preview and stem mixer — new `MultitrackEditor`/`StemMixer`/`WaveformView`
frontend components + `region`/`stems`/`beats` API routes under `frontend/app/api/produce/`, plus
backend `src/api/region_tools.py` and `src/api/routers/produce.py`) and a same-day `fix:`
(`8528dfc`, route region tools through one dispatch path that honors kwargs — refactored
`src/production/big_flavor_mcp.py` and `src/agent/big_flavor_agent.py` tool dispatch, +282
lines of new dispatch tests), plus the v0.14.0 memory chore. Published GitHub Release with
auto-generated notes anchored to `v0.14.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.15.0. Notified linked closed issue
#70. Sanity gate: backend restart came up **healthy** after model warm-up (CLAP model re-fetches
from Hugging Face on cold start — expected, not an error); the only log error was the same
pre-existing `PermissionError` on `/app/streaming/playlist/radio.m3u` in the radio loop noted since
v0.14.0 (local volume-mount permission issue, unrelated to this range). Frontend `npm run build`
**passed**, including the new `/produce/[songId]` region/stems/beats API routes. Proceeded per
Step 4.5.

### 2026-07-13 — Release `v0.14.0` (release-manager)
Cut **`v0.14.0`** from `main` (HEAD `223d816`), a **minor** bump from `v0.13.0` — the 11-commit range
is a run of production-pipeline `feat:` commits across five merged PRs: region time-range + wet/dry
strength on cleanup tools (#71, issue #65), Demucs stem separation with per-stem remix (#72, #67),
note-level key-aware pitch-correction auto-tune (#73, #68), trim-to-selection + non-stationary
(adaptive) noise reduction (#75, #66), and beat-level tempo quantization / `correct_beats` MCP tool
(#74, #69) — plus their merge commits and the `chore: record v0.13.0` memory commit. Range touches
only backend/production code (`src/production/`, `src/api/`, `database/`, `backend_api.py`, a stems
migration, `docker-compose.yml`, `requirements-api.txt`) and tests — no frontend. Published GitHub
Release with auto-generated notes anchored to `v0.13.0`:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.14.0. Notified linked closed issues
#65–#69. Sanity gate: backend restart booted clean (health 200; the `PermissionError` on
`/app/streaming/playlist/radio.m3u` in the radio loop is a pre-existing local volume-mount permission
issue, not a startup/import error and not in this range — note the prior asyncpg
`DatatypeMismatchError` did **not** recur this run). Frontend `npm run build` first failed on a stale
`.next/dev/types/validator.ts` referencing a renamed auth route (`[auth0]` vs the actual
`[...google]`); since the range changes zero frontend files (last frontend commit `059df70` predates
v0.13.0), cleared `.next` and rebuilt — **passed**. Proceeded per Step 4.5.

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

### 2026-06-20 — First tagged release `v0.1.0` (release-manager)
Adopted `vX.Y.Z` git-tag versioning. Cut the **first release `v0.1.0`** from `main` (HEAD `775e747`,
44 commits, no prior tag) and published a GitHub Release with auto-generated notes:
https://github.com/Robby2D2/big-flavor-band-agent/releases/tag/v0.1.0. No issues notified — the
initial history has no `#NN` PR references in commit subjects, so there were no linked closed issues.
Sanity gate skipped (Docker stack not running locally — infra, not a `main` error). The hygiene work
on `fix/container-config-hygiene-11` (`97c4eb6`) was **not** merged to `main` and is correctly out of
this release.
