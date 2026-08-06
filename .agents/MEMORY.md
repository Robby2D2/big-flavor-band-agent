# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-08-01: routine release-manager version-bump entries moved to
> [memory/releases.md](memory/releases.md); the 2025-11 project-genesis timeline and two older one-off
> incident writeups moved to [memory/history_2025_2026.md](memory/history_2025_2026.md). This file now
> holds only the recent, still-load-bearing entries.

---

### 2026-08-04 — Stem console loaded ~260 MB per tab open to draw waveforms; now ~15 KB of peaks + Opus playback copies
**The measurement that drove this:** stems are uncompressed Demucs WAV — `produced/1140/stems/9/bass.wav`
is 43.8 MB, a six-stem set ~262 MB, and a *cleaned* version (if selected as the source) 62 MB. All of
it was downloaded and `decodeAudioData`'d on every produce-tab open. But `WaveformView` only ever fed
`computePeaks(buffer, width)` — a per-pixel min/max envelope. ~260 MB was moving to draw ~15 KB.

Split into two independent server resources:
- **`src/production/waveform_peaks.py`** — 2000-bucket min/max envelope, quantised to ints in ±127,
  cached in a new `waveform_peaks` JSONB column on both `song_stems` and `song_versions`. Streams via
  `sf.blocks` rather than `librosa.load`: loading whole files would spike ~85 MB per concurrent call
  on a box also running Demucs. Verified bit-identical to a naive full-load pass (the block-seam
  handling is the only tricky part — bucket boundaries don't align with read boundaries). Measured
  0.86 s cold / **0.005 s warm** on a 43 MB stem.
- **`src/production/audio_preview.py`** — ffmpeg → Opus at 96k for browser playback only, ~15x
  smaller. `/audio` still serves the real WAV and is what every DSP tool and the A/B fidelity control
  reads.

**Three design points worth keeping:**
1. **`version` is checked on read.** A cached envelope from an older `PEAKS_FORMAT_VERSION` is treated
   as absent. That is what made "no backfill script" safe — bumping the constant re-derives the whole
   catalog lazily.
2. **Preview paths key off the source file path, never a row id.** Produce never overwrites audio in
   place (a re-clean writes a new timestamped file; a re-separation a new set dir), so a path-keyed
   preview physically cannot go stale — no invalidation logic at all. Version previews live in a
   shared `produced/previews/` because the catalog mount is read-only.
3. **A row id can outlive its audio.** `replace_song_version_audio` swaps `audio_path` under a stable
   version id, and `add_stem`'s `ON CONFLICT` reuses a row on a retried job — both now NULL
   `waveform_peaks`. Same reason the version peaks/preview proxies are uncached while the stem ones
   are `immutable`.

**The frontend trap:** `maxDuration` was derived *solely* from decoded buffers, and it gates the
transport, every `WaveformView`'s `duration`, and all seek/region math. Drawing before decoding meant
duration had to come from the server (it ships in the peaks payload). Related: `useStemPlayback.play()`
silently no-ops with no buffers, so the transport is now gated on `playbackReady` — otherwise the
button looks live during the prefetch window and does nothing. The full mix's *audio* is no longer
prefetched at all (it starts muted). Honest limit: this fixes bandwidth and decode time, **not** the
~640 MB of `AudioBuffer` RAM — `decodeAudioData` yields float32 PCM whatever the source codec.

Also: `frontend` dev dependencies (vitest et al.) were declared but never installed, so the existing
`lyricTimings`/`LyricsFollower` tests had never actually run. `npm install` fixed it; 33 tests pass.

**Two bugs the live check caught that the tests could not.** Both are worth remembering as a pattern:
a monkeypatched dependency means the real command is never exercised.
1. **ffmpeg picks its muxer from the output filename's extension.** The encode writes to a `.part`
   temp file so the publish is an atomic rename — but ffmpeg can't infer a format from `.part`, so
   *every* real transcode failed and `/preview` 503'd. Fixed with an explicit `-f ogg`. The test
   asserted the temp suffix but never that the command could produce output.
2. **A container restart is required for a hot-reload change to reach the running uvicorn.** The
   first re-measurement still logged the pre-fix command line because the process had the old module
   loaded — `./src` is volume-mounted, but the import is not re-evaluated.

**Empty stems were still displaying** (the original request that started this work). The console hides
stems tagged `silent`, but `instrument_tagging` judged silence on per-window RMS against a -80 dBFS
floor, and an empty Demucs stem is *bleed*, not digital silence — song 1140's bass and piano measured
-61 dBFS RMS, ~9x over that gate, so they scored as present-but-unrecognised. Now judged on **peak**
via a new pure `is_silent()`: empty stems peak -56..-52 dBFS, the quietest genuinely-present
instrument peaks -23.2 dBFS, so `SILENCE_PEAK` = -40 dBFS sits mid-gap. RMS provably cannot do this —
1650's sparse-but-real piano is -54.7 dBFS RMS (within 6 dB of empty) but -23.2 dBFS peak. Verified
against all 12 stems on disk; re-tag existing rows with `POST /api/produce/stems/{id}/identify`.

Net measured effect on a produce tab open for song 1140: **262.7 MB -> 11.2 MB (23.5x)**, since the
two hidden stems are no longer fetched at all, and waveforms paint from 45 KB of peaks.

### 2026-08-02 — Stem console: full mix as a row, a real transport, and instrument tagging for stems Demucs can only call "other"
Two related pieces of work on `/produce/[songId]` → Audio processing.

**Console + transport.** The full mix is now the console's first row — a frontend-only pseudo-stem
(`FULL_MIX_STEM_ID = -1`) whose fixes *are* the master-scoped fixes, so the whole song is played,
analyzed and fixed through the same UI as its parts and no backend code knows it exists. It starts
**muted** (the stems already sum to it). "Play stems" became a media-player transport: play/pause
holds the playhead, `seek` restarts every source at a shared origin so stems stay sample-synced
across a scrub, and the full-track waveform takes a click or drag. `WaveformView` gained `onSeek`
(mutually exclusive with `selectable` — a drag can't both scrub and draw a region). Dropped
`toggleAudition`/`auditionId` from `useStemPlayback`: dead code, never consumed.
Also fixed two things the console said while working: stem audio was decoded serially and committed
only once *every* file landed (so a saved stem set sat empty for a long time showing "not analyzed
yet" twice) — now fanned out with per-row commits, a spinner per row, and a `decodedUrls` ref so
re-analysis doesn't re-download; and rows can be analyzed one at a time, which made "clean" vs
"not analyzed" honest per row instead of one global flag.

**Instrument tagging (the banjo problem).** User asked whether other instruments (banjo, mandolin)
could be auto-detected and split out. They can't be *split*: Demucs' source list is baked into the
model weights, so `htdemucs_6s` emits exactly vocals/drums/bass/guitar/piano/other and adding names
to `stemColors.ts` changes only a swatch colour. But nothing is lost — the stems sum back to the
mix, so a banjo is present, just inside `other`. The gap is **naming, not coverage**, so we tag
rather than separate: `src/production/instrument_tagging.py` runs an AudioSet tagger
(`MIT/ast-finetuned-audioset-10-10-0.4593`) over each stem, maps AudioSet's comma-separated display
names ("Violin, fiddle") onto a curated vocabulary, and takes the **max** across evenly-spaced
non-silent windows — mean would wash out an instrument that only plays one section. `silent: true`
is a real answer (a band with no piano still gets a piano stem). Producer can override the label
(`song_stems.display_name`, migration `10`); `name` stays the Demucs source name because that's what
the fix tools resolve against. Tagging runs *after* the set is marked complete, best-effort, so it
can't fail a separation or delay the waveforms. Verified live in-container on song 1650: guitar stem
→ Guitar/Electric guitar, vocals → Vocal/Male vocal, `other` → Flute/Organ/Fiddle.
The rejected alternatives (query-based separation à la AudioSep; fine-tuning Demucs on isolated
multitracks the band doesn't have) are recorded in ARCHITECTURE.md's decisions log.

> Note: `docker-compose.yml` gained `HF_HOME` + an `hf_models` volume so the HF checkpoints (CLAP,
> the tagger) stop re-downloading on every recreate. That needs `docker-compose up -d backend`, not
> a plain `docker restart`.

### 2026-08-02 — Timed lyrics (phase 1): follow-along highlighting + vocal-isolated transcription + vitest
Lyrics can now be followed along while a song plays. The enabling discovery: **Whisper was already
computing the timings and we were throwing them away** — `lyrics_extractor.transcribe_audio()` built a
`segments` list with `start`/`end`/`text`/`confidence`, and `lyrics_jobs._blocking_extract` returned only
the joined text. Line-level sync therefore cost no extra compute.
- **Storage:** new `song_lyric_timings` table (migration `11`, plus `ensure_song_lyric_timings_table()`
  called from the lifespan like `song_versions`/`song_stems`). One JSONB `lines` document per song
  (UNIQUE on song_id) — always read whole for playback, never queried by field. Lyric **text** stays in
  `text_embeddings` (content_type `lyrics`) as the single search source of truth; timings are a derived
  sidecar. Deliberately *not* a second `text_embeddings` row: that table is keyed
  `UNIQUE(song_id, content_type)` around an embedding column and lyric search filters on content_type.
- **Vocal isolation, pulled forward from phase 2** at the user's request, so the ~1,300-song
  re-extraction only has to run once. Extraction now prefers isolated vocals: it reuses an existing
  completed `vocals` stem (issue #67's `song_stem_sets`/`song_stems`, via `db.get_vocals_stem_path()`)
  when the file is still on disk, else runs Demucs in-job; the raw mix is only a fallback.
  `word_timestamps=True` was pulled forward for the same reason — the words are persisted now even
  though phase 1's UI only lights up lines.
- **Two real bugs found in `lyrics_extractor.py` while wiring this up:** (1) `separate_vocals()` picked
  the vocals stem by hardcoded index `sources[3]`, which silently transcribes the wrong stem for any
  model whose source order differs — now looked up by name; (2) `extract_lyrics()` gated separation on
  `self.demucs is not None`, making `separate_vocals=True` a **silent no-op** whenever the extractor was
  built with `load_demucs=False` (exactly how the job constructs it) — `separate_vocals()` lazy-loads,
  so the gate is gone.
- **Staleness:** hand-editing lyrics invalidates timings, so `PUT .../lyrics` compares
  `lyrics_jobs.lyrics_signature()` (case/punctuation/whitespace-normalized word sequence) and marks the
  record `stale`. Reflow and capitalization edits deliberately keep timings `current`. Stale timings are
  hidden during playback rather than highlighting the wrong words; `LyricsPanel` surfaces the state.
- **API:** new **listener-scoped** `GET /api/songs/{id}/lyrics/timed` (in the search router, next to the
  existing public lyrics route) + a matching BFF route. This is the point that would have been easy to
  get wrong: the editor lyric routes live under `/api/produce/*` behind `require_role("editor")`, which
  would have locked every ordinary listener out of their own player. The produce GET/PUT also return
  `timings` for the editor.
- **Frontend:** pure logic in `lib/lyricTimings.ts` (`findActiveLine` binary search, `findDisplayLine`
  which holds the last line through instrumental gaps, `findActiveWord`, `isFollowable`), `useActiveLyric`
  hook, and a time-source-agnostic `LyricsFollower` component (takes seconds, not a player — so the same
  component can serve the `<audio>` player, the produce page's AudioContext `playhead`, and the radio's
  polled position). Wired into `AudioPlayer` behind a Lyrics toggle, driven by **rAF** rather than
  `timeupdate` (which only fires ~4x/sec — fine for a seek bar, visibly behind for words).
  Manual-scroll detection suspends autoscroll for 4s with a "Jump to current" button.
- **Testing:** added **vitest** — the project's first frontend test runner (`vitest.config.mts` + jsdom +
  React Testing Library, `npm test`). 26 frontend tests. Backend: new `tests/test_lyrics_jobs.py` plus
  timed-lyrics cases in `test_produce_router.py`/`test_api_routers.py`.
- **Fixed in passing:** `tests/test_lifespan.py` was already failing on `main` — its `FakeDatabaseManager`
  never gained `ensure_song_stems_tables` after issue #67, so the lifespan tests died with AttributeError.
  The fake now covers all three ensure-calls and asserts them, so it can't silently rot again.
- **Known gap:** `npm run lint` is broken repo-wide — Next 16 removed `next lint`, so the script now
  reads "lint" as a directory name and errors. Pre-existing and unrelated to this work, but it means the
  documented frontend lint gate isn't running; needs a migration to flat-config `eslint .`.
- **Backfill (added same day):** `scripts/backfill_lyric_timings.py` re-extracts the catalog. Design
  points worth keeping: (1) `lyrics_jobs.extract_and_store()` was factored out as the *one* seam both
  `LyricsJobManager._run` and the script call, so the UI button and the batch can't drift; (2) the
  script loads Whisper **once** and passes the extractor down via `_blocking_extract(extractor=…)` —
  the per-request path builds one per call, which over ~1,300 songs is hours of pure model loading;
  (3) resumability needs no state file — a `song_lyric_timings` row *is* the checkpoint, so a JSON
  ledger is only needed for failures (so a broken track isn't retried every resume); (4) SIGINT stops
  after the current song rather than mid-write. **The non-obvious hazard it guards:** storing lyrics
  re-embeds them, and `_embed_text` silently falls back to a zero vector when sentence-transformers
  is missing (as it is in the host venv) — a catalog-wide run there would flatten every lyric
  embedding and destroy lyric search, so the script hard-refuses (exit 2) unless the model loaded.
  Run it in-container: `docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings`.

---

### 2026-08-01 — Claude Design "Console" redesign of the Audio Processing tab: dark theme + per-stem review queue
Implemented a full Claude Design mockup (imported as a `claude.ai/design` canvas export, `claudedesign.zip`)
that replaced the `/produce/[songId]` Audio processing tab's "checkbox list of tools + Gentle/Moderate/
Aggressive intensity dial" with a dark "Console" studio theme and a **review-queue** workflow: one
analysis pass produces one card per detected fix, each pre-filled with the tool's own real measured
numbers (not an intensity bucket), grouped by stem, with per-card Accept/Adjust/Skip and a single
"Accept all & save version." User explicitly chose the larger scope on both open questions: build
real **per-stem** analyze/apply (not whole-song-only), and a **whole-app** dark theme (not just this
tab). Delivered in four phases, each independently verified.
- **Phase A (theme foundation):** `frontend/tailwind.config.ts` → `darkMode: 'class'` + Console color
  tokens (`canvas/panel/raised/well/signal/confirm/attention/text` + `stem.{vocals,drums,bass,other,
  guitar,piano}`); `app/layout.tsx` loads IBM Plex Sans/Mono via `next/font/google` and sets a
  permanent `className="dark"` on `<html>` (no light/dark toggle — the mockup has no light variant);
  `globals.css` simplified to unconditional dark `--background`/`--foreground`; deleted the dead,
  unimported `app/tailwind.css` (leftover Tailwind v4 file). `Header.tsx`/`UserButton.tsx` restyled
  onto the tokens. Flipping `darkMode:'class'` also makes every pre-existing `dark:gray-900`-style
  class elsewhere in the app activate unconditionally (previously gated on OS `prefers-color-scheme`).
- **Phase B (backend, no DSP changes needed):** `AudioTool.analyze()`/`apply()`
  (`src/production/toolkit.py`) turned out to already be file-path-agnostic — they only ever see a
  `file_path`, never "the song." So per-stem support was pure router work in
  `src/api/routers/produce.py`: `ToolRunRequest` gained `stem_id`; new `_resolve_tool_source_path`
  resolves a stem's own audio file (via `db.get_stem`→`db.get_stem_set`, 404 on song-ownership
  mismatch) ahead of the existing version-based resolution; stem-scoped `apply` is always a
  preview-only render (never creates a version). New `StemFixSpec` + `_chain_apply_tools` sequentially
  chain-apply a list of fixes (step N's output feeds step N+1); new routes
  `POST /api/produce/stems/{stem_id}/preview-chain` (audition one stem's enabled fix chain) and
  `POST /api/produce/accept-fixes` (chain-apply every stem's fixes, remix at unity gain via the
  existing `stem_separation.remix_stems`, then chain-apply master-bucket fixes — `preview=true` for
  "Preview full mix first," `preview=false` to save a version, matching the existing
  `save_candidate_version` seam). New `AudioTool.confidence_tier(value, high, worth, higher_is_worse)`
  static helper buckets a tool's own measured magnitude into `"high"`/`"worth_a_listen"`/`None`; added
  a `confidence` key to the 7 tools with real `analyze()` overrides (reduce_noise, apply_eq,
  remove_hum, trim_silence, normalize_audio, apply_mastering, correct_beats — thresholds tuned
  per-tool, e.g. noise floor dB, EQ adjustment count, beat-detection's own `mean_confidence`).
  `correct_pitch`/`match_tempo`/`remove_artifacts` still have no `analyze()` override (always
  `recommended: False`) and so never produce a fix card — unchanged, pre-existing, out of scope.
  New `tests/test_produce_stem_tools.py` (7 tests: confidence tiering both directions, stem-ownership
  404, chain-apply empty-passthrough and output-feeds-next-input wiring) — all pass, plus the existing
  30 production tests unaffected.
- **Phase C (frontend, new component tree):** Retired `MultitrackEditor.tsx` (1319 lines) and
  `StemMixer.tsx` (524 lines) — deleted outright, no remaining imports — since the review-queue
  interaction model is different enough that patching in place would have compounded complexity.
  New tree under `frontend/components/produce/audio/`: `VersionBar`, `StemConsole` (per-stem
  sparkline + chain-of-pills + mute/solo/gain), `StemDetailPanel` (A/B waveform, region drag-select),
  `FixQueue`/`FixCard` (one card per fix, confidence tag, Hear it/Adjust/on-off), `AdvancedDrawer`
  (per-param sliders driven by `GET /api/produce/tools`' declared param metadata), `ResultSidebar`
  ("fixes on" count, Accept all & save version, Preview full mix first), `LyricsCard` (thin restyled
  wrapper — `LyricsPanel`'s fetch/save/re-extract logic reused verbatim, lyrics folded into the
  sidebar instead of a separate top-level tab), `fixCopy.ts` (tool+findings → plain-English card
  copy), `stemColors.ts`. `useStemPlayback.ts` extracts `StemMixer`'s sample-synced group-playback
  engine verbatim (genuinely reusable Web Audio sync logic). `WaveformView.tsx` gained an additive
  `overlays` prop (colored spans per fix location) alongside its existing `region`/`trimRegion`.
  New `frontend/hooks/useProcessingQueue.ts` is the data-flow hub: fans out per-stem × per-tool +
  master-bucket `analyze` calls (capped at 3 concurrent), assembles one `FixEntry` per
  `recommended:true` result, and drives accept/preview. **Caught and fixed one real bug during
  self-review:** the "Re-separate" button initially just re-ran analysis against whatever stem set
  already existed (`waitForStemSet` short-circuited to the latest *complete* set even after kicking
  off a fresh Demucs job) — fixed by parameterizing it with a `forceNew` flag that polls for the
  *newest* set by id instead, exposed as a distinct `reseparateAndAnalyze`.
  Every `POST /api/produce/*` call goes through a Next.js BFF proxy route
  (`frontend/app/api/produce/**/route.ts`, each whitelisting which body fields it forwards + attaching
  `backendAuthHeaders`) — **the existing `tools/{tool}/analyze` and `.../apply` proxies did not forward
  the new `stem_id` field** and had to be updated, and two new proxy routes
  (`accept-fixes/route.ts`, `stems/[stemId]/preview-chain/route.ts`) had to be created; the candidate-
  audio streaming URL is `/api/produce/clean/preview?path=` (not `/api/produce/preview`, which has no
  frontend proxy — a naming trap the old `MultitrackEditor` code had already worked around).
- **Phase D (sweep + cleanup):** Migrated the remaining light-themed pages
  (`app/{page,search,radio,edit,admin,admin/produce,produce,produce/[songId]}.tsx`) from ad-hoc
  `bg-white dark:bg-gray-800`-style pairs onto the Phase A tokens via systematic `replace_all`
  substitutions of the handful of recurring patterns (`bg-white dark:bg-gray-800`→`bg-panel`,
  `text-gray-900 dark:text-white`→`text-text`, etc.); left accent-colored elements (blue/green/red
  buttons and badges) as-is — they already read fine against the dark canvas, and pixel-matching every
  one wasn't worth the churn this pass.
- **Verification:** `npm run build` clean after every phase (TypeScript catches prop-shape drift
  across the new component tree — no runtime type errors slipped through); `next lint`/`npm run lint`
  is broken repo-wide under Next 16 (`next lint` was removed upstream) — pre-existing, confirmed via
  `git stash` before this work, not something this change caused. **Docker Desktop was not running in
  this environment** (`docker ps` failed to connect throughout), so the full interactive workflow
  (real stem separation, real analyze results, a real Accept-all render) was **not** manually exercised
  end-to-end — verification leaned on `npm run build`/TypeScript, `pytest` (37 passing: 7 new + 30
  existing, no regressions), reading the OpenAPI schema to confirm new routes registered, and a
  careful manual code-flow review (which is what caught the re-separate bug above). A human should do
  one real walkthrough (pick a version → Start analysis → toggle a few fixes → Accept all) before
  trusting this in production.

### 2026-07-31 — Per-tool audio API: one file per tool + declare-params → analyze → apply
Refactored the ~3,900-line `src/production/big_flavor_mcp.py` monolith (where every tool's schema,
routing, and implementation lived in three separate places) into a **per-tool registry** so adding a
tool is "add one file", and gave each tool a two-phase **analyze → apply** contract the producer can
drive per tool. User-approved plan, class-per-tool + full-stack + independent per-tool analyze.
- **New modules:** `src/production/toolkit.py` (`AudioTool` base, `Param` schema, `ToolContext`,
  `REGISTRY`, `@register`), `audio_io.py` (load/write/per-channel + WAV subtypes), `analysis.py`
  (key/beat/pitch/hum/LUFS helpers + `load_for_analysis`/`detect_hum`/`measure_integrated_lufs`/
  `perform_audio_analysis`), and `tools/*.py` — 13 one-file tools (trim_silence, reduce_noise,
  remove_hum, apply_eq, remove_artifacts, correct_pitch, correct_beats, match_tempo,
  normalize_audio, apply_mastering, create_transition, analyze_audio, get_audio_cache_stats).
- **Server is now a thin host:** `list_tools()`/`dispatch_tool()` are generic loops over `REGISTRY`;
  `analyze_tool()` runs the read side; a `__getattr__` shim maps `server.<tool>(...)` → the tool's
  `apply` bound to a shared `ToolContext`, so existing tests + `auto_clean_recording` (which now
  orchestrates the registry via the shim) keep working unchanged.
- **Per-tool `analyze()`** (independent, not a shared bundle): trim/noise/hum/eq/normalize/master/
  beats each inspect only their own concern and return `{recommended, params, findings, reason}`
  (as of 2026-08-01, also `confidence` — see the entry above); others inherit the base stub.
- **Monolith retired:** `analyze_and_recommend_processing` and `auto_clean_recording` are registry
  tools now (`tools/analyze_recommend.py`, `tools/auto_clean.py`, both `hidden_from_editor=True`).
  The server class dropped from ~3,900 to ~190 lines and carries no audio logic.
- **Region whitelist folded** onto the registry: `region_tools.py` derives each friendly tool's
  forwardable params from the target tool's declared `Param`s (single source of truth).
- Full production test suite passing at the time (143 passed, 1 skipped, 1 pre-existing unrelated
  failure).

### 2026-07-31 — Restore Pitch correction & Tempo/beat correction to the per-step `/produce` editor (issue #82)
Fixed a regression where PR #81's `StepKey`/`STEP_DEFS` rework silently dropped Pitch correction and
Tempo/beat correction from the (now-retired) `MultitrackEditor` UI, even though the backing tools
(`correct_pitch`, `match_tempo`) still worked. `auto_clean_recording` gained two opt-in steps (no
analysis recommends either, so both default off): `pitch` (region-scoped, key-aware auto-tune) and
`tempo` (whole-track time-stretch to an explicit `target_bpm`, forced off under a region like
Normalize/Master — it has no region parameter). Orchestration-only; neither tool's algorithm changed.

### 2026-07-31 — Per-step tunable cleaning params + unified whole-song/region flow (issue #77 follow-up)
Replaced the (now-retired) `MultitrackEditor`'s single global Intensity dropdown with per-step
recommendations and unified "Whole song"/"Region" into one analyze → detected-issues → per-step
controls → Preview/Clean pipeline (a region is a scope — `start_s`/`end_s` — not a different tool).
`analyze_and_recommend_processing` returns a per-step `recommended_intensity` derived from its own
measurements; `auto_clean_recording` gained `step_params` (explicit per-step overrides that always win
over the aggressiveness-scaled recommendation) and region bounds, with Normalize/Master always
skipped under a region and Trim routed through `trim_silence`'s own scoped silence-trim so a
mid-track selection can never delete audio outside it.

### 2026-07-12 — Pipeline concurrency standards ported from soccer-assistant-coach + GitHub Actions sweep
**AGENTS.md** gained a **Concurrency** section (re-check before write; lost races are benign skips,
not errors; writers claim / readers re-check; never touch a dirty human working tree) and now
documents two run environments — local Windows and headless GitHub Actions (`$GITHUB_ACTIONS`=`true`;
no Docker stack in CI, so agents run targeted pytest + frontend lint/build and honestly report what
wasn't verified). **developer** got a `dev-agent:claim` protocol + dirty-tree guard + pre-push PR
re-check; **cpo/pm/qa** re-fetch markers before posting; **release-manager** got a dirty-tree guard +
tag-idempotency re-check. New `.github/workflows/fix-issue.yml` runs the sweep via
`anthropics/claude-code-action` on issue-opened/reopened + human comments + manual dispatch.

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
- **Frontend theme (as of 2026-08-01):** dark-only "Console" design system, `darkMode: 'class'` +
  permanent `dark` class on `<html>` — there is no light mode and no toggle. Design tokens live in
  `frontend/tailwind.config.ts` (`canvas/panel/raised/well/signal/confirm/attention/text`, plus
  `stem.*` accent colors). Every `frontend/app/api/produce/**/route.ts` is a hand-written BFF proxy
  that whitelists which body fields it forwards to the backend — adding a field to a backend request
  model does **not** automatically reach the browser; the matching proxy route needs the same field
  added explicitly.
