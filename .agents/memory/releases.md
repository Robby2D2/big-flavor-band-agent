# Release History — Big Flavor Band Agent

Rolling, dated record of every `vX.Y.Z` release cut by the release-manager agent. Moved out of
`MEMORY.md` during a 2026-08-01 prune (routine/repetitive entries, low ongoing signal once a release
is out). Newest at top.

---

*The `v0.19.0` → `v0.17.0` entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-09-27 prune.*

### 2026-09-26 — Released v0.19.0 (minor bump — radio truth-telling, session import, the requirements record)
Tagged `main` at `eeeb686` as **v0.19.0**. Minor rather than patch: the range is not only fixes —
Reaper rehearsal-session scanning/import arrived as `feat:` with **migration 18**, and
`docs/requirements/` landed as the product contract. 10 releasable commits (the v0.18.0 memory chore
filtered out). PRs #99/#100 (issues #96/#97) finally landed here after being approved-but-unmerged at
v0.18.0, joining #103 (#101) and #105 (#102). Four issues notified. Sanity gate ran in full: backend
restarted to `Startup complete: backend ready to serve requests` with no errors, frontend build clean.

**Writing the deploy summary turned up two ways the deploy script quietly under-delivers**, both now
called out in the Release notes and on the issues:
- **`deploy-production.sh` runs a plain `docker-compose build`, which cannot pick up `radio.liq`** —
  BuildKit caches that `COPY` layer (the `AGENTS.md` no-cache rebuild exists for exactly this). This is
  the first release where it bites: the harbor listener *is* the #101 fix, so a normal deploy ships the
  old config, the endpoint never exists, and Now Playing fails **silently** rather than loudly.
- **The script prints "Set up the database with migrations" and contains no migration step.** Worse,
  `recording_sessions` is *not* startup-ensured the way `song_versions` / `song_stems` /
  `song_lyric_timings` are, so migration 18 is genuinely manual or `/produce/sessions` 500s. Worth
  remembering: "ensured at startup" covers only three tables, not the schema.

Two settings ride along with the checkout rather than needing `.env` edits (`LIQUIDSOAP_HARBOR_URL`,
the writable `./audio_library/sessions` mount), and `X-User-Id` needs **no** new secret — but it is
only believed when `BACKEND_API_SECRET` verifies, so a mismatched secret in prod turns "remove the
song I added" into a blanket rejection.

**Two caveats stated plainly in the notes rather than smoothed over.** Neither radio change has been
seen in a browser by a human — both rest on unit tests plus live API/stream probes, with QA's
recommended editor-and-listener click-through on `/radio` still outstanding. And issue #104 is open:
`fallback_music` is unreachable, so an empty queue serves silence and **RAD-02 remains unmet**. The
notes say it in one line worth keeping: this release makes the radio *honest* about what is playing, it
does not yet make it *reliable* about always playing something.

---

### 2026-09-22 — Released v0.18.0 (kept stems + standalone Separate stems)
Tagged `main` as **v0.18.0** — a minor, not a patch, because PR #95 adds capability that did not
exist before: a save keeps the per-stem audio it just rendered as the new version's stem set, and
**Separate stems** became its own button beside Start analysis. Migration 17 (`song_stem_sets.origin`)
ships with it; **migrations 16 and 17 are already applied to the live database**, so a deployer does
not need to run them. Sanity gate passed (backend booted clean, frontend `npm run build` succeeded).
PR #95 closed no issues, so no issue notifications went out. Production is still on v0.17.3 — this
one is tagged and **waiting on a human deploy**, unlike the previous two releases. PRs #99 and #100
are QA-approved but unmerged and are not in this release.

---

### 2026-09-21 — Released v0.17.3 (patch bump — the version-scoped stems fix, tagging code already live)
Tagged `main` at `1da724e` as **v0.17.3**. Patch rather than minor: the range is PR #94 alone (plus
its merge) — the produce console showed the song's *newest* stems instead of the selected version's,
so a cleaned mix was being reviewed, and measured, against the original's stems. It is a correctness
fix on shipped behaviour with no new capability: no `feat:` commit, no `enhancement` label, and the
PR closes no issue (issue-less fix), so **no issues were notified**.

Sanity gate ran in full: `bigflavor-backend` restarted to `Startup complete: backend ready to serve
requests` with no errors, and `npm run build` compiled the frontend clean.

**The tag trailed the deploy again** — `1da724e` was built, deployed and verified in production
before this run, so the Release body says "already deployed" rather than "ready to deploy". Second
time in three releases (see v0.17.1); the tag history is a record of what was released, not of when
it went live.

PR #95 (keep the stems a save rendered; separating as its own button) was approved but **not merged**
at tag time, so it is not in v0.17.3 — same shape as v0.17.0/#90, and it lands in the next release.

---

### 2026-09-21 — Released v0.17.2 (patch bump — the pitch gate scope fix, plus a release-loop fix)
Tagged `main` at `68febac` as **v0.17.2**. Patch rather than minor: the range is PR #92 (issue #91 —
one shared monophony measurement across analyze/apply, and a fix-that-fell-short now reported on a
fresh save, not just a cached one) and PR #93 (agent config only). Every commit is `fix:`-prefixed,
#91 carries no `enhancement` label, and neither PR opens new capability — both close gaps in work
already shipped. Issue #91 notified.

Sanity gate ran in full: `bigflavor-backend` restarted to `Application startup complete` with no
errors in the log, and `npm run build` compiled the frontend clean.

**First release cut with Step 2's release-chore filter in place** (PR #93, merged minutes before this
run). The raw range held 6 commits; the v0.17.1 memory chore was excluded, giving 5 releasable — so
the count reflected real work rather than the previous release's own paperwork. Unlike v0.17.1, this
tag *precedes* the deploy: a human deploys immediately after, so the "ready to deploy" wording on
#91 is accurate as posted.

---

### 2026-09-21 — Released v0.17.1 (patch bump — the pitch/click work v0.17.0 just missed)
Tagged `main` at `1fc1382` as **v0.17.1**. Patch rather than minor: the whole range is PR #90
(issue #89) plus the v0.17.0 memory commit and its merge, and every commit in it is `fix:`-prefixed
with no `enhancement` label — it finishes work already scoped, rather than opening new capability.
It is the tail of v0.17.0: that release was cut while #90 was approved-but-unmerged, and this one
picks it up. Issue #89 notified.

Sanity gate ran in full: `bigflavor-backend` restarted to `Application startup complete` and healthy,
`npm run build` compiled clean.

**The tag trailed the deploy this time.** A human had already deployed and verified `1fc1382` in
production before the release ran, so v0.17.1 names what was live rather than queuing it. Harmless,
but worth knowing when reading the tag history: a tag date here is not necessarily a deploy date.

---

### 2026-09-20 — Released v0.17.0 (minor bump — 58 commits, first release since v0.16.2)
Tagged `main` at `2412341` as **v0.17.0**. Minor rather than patch: the range carries real new
capability, not just fixes — timed lyrics with follow-along highlighting, editor invite links (and
the auth holes closed building them), the full mix + real transport in the stem console, the
per-tool audio registry with its `analyze`/`apply` contract, per-step tunable cleaning, search
ranked on what a song *is* (with "why did this match" explanations), and the fix picker offering
every DSP tool rather than only the four with detectors. Issues #82 and #86 notified.

Sanity gate ran fully this time: `bigflavor-backend` restarted to `Application startup complete`
and healthy, and `npm run build` compiled the frontend clean. Note that PR #90 (pitch/click
detection, issue #89) was approved but **not merged** at tag time, so it is *not* in v0.17.0 — it
lands in the next release.

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
