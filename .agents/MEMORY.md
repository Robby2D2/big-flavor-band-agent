# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-09-19: the session-cookie signing entry moved to
> [memory/auth_access.md](memory/auth_access.md), joining the editor-invites entry it was the
> companion to.
>
> Pruned 2026-09-18 (457 lines → ~200): the prod-deploy entry moved to
> [memory/deploy_ops.md](memory/deploy_ops.md); the search-accuracy rework to
> [memory/search_rag.md](memory/search_rag.md); the missing-BFF-route and edge-proxy-timeout entries
> to [memory/frontend_bff.md](memory/frontend_bff.md); editor invites to
> [memory/auth_access.md](memory/auth_access.md); the Start-analysis stem-reuse rule and the
> waveform-peaks rework to [memory/produce_console.md](memory/produce_console.md).
>
> Pruned 2026-09-14: the `/produce` per-tool API and stem-console entries (2026-07-31 →
> 2026-08-02) moved to [memory/produce_console.md](memory/produce_console.md); the 2026-07-12
> pipeline-concurrency entry moved to [memory/history_2025_2026.md](memory/history_2025_2026.md).
>
> Pruned 2026-08-01: routine release-manager version-bump entries moved to
> [memory/releases.md](memory/releases.md); the 2025-11 project-genesis timeline and two older one-off
> incident writeups moved to [memory/history_2025_2026.md](memory/history_2025_2026.md). This file now
> holds only the recent, still-load-bearing entries.

---

### 2026-09-26 — Now Playing is derived from the stream; the backend's clock is gone (issue #101)
The radio page named its song from a timer that had no connection to the audio. `update_radio_position()`
added wall-clock time to a position and rolled over when it passed the catalog `duration`; Liquidsoap
played `radio.m3u` on its own schedule and never reported back. **Confirmed live before writing any
code:** Icecast was broadcasting *So Tired* while the head of the playlist was *Fake Plastic Trees*.

- **Liquidsoap already knew and had no way to say it.** `source.on_track` remembers the metadata of
  each track that starts, and `harbor.http.register.simple` serves it as
  `{filename, title, source, elapsed, remaining}` on container-internal port 8080, with `POST /skip`
  calling `source.skip`. All five functions verified against `savonet/liquidsoap:v2.2.4` and the whole
  script `liquidsoap --check`ed before every rebuild — which must be the **no-cache** rebuild, a plain
  restart never picks `radio.liq` up.
- **Pulled, not pushed.** The loop asks each tick, so a backend restart needs no replay and no stored
  staleness window — verified by stopping Liquidsoap for 12s (state went `stream_known: false`, one
  WARN, no repeats) and starting it again (state re-agreed with the air on its own, RAD-04/PLAT-12).
- **The filename is the identity.** Icecast's `/status-json.xsl` only carries an ID3 title, which
  cannot be mapped back to a catalog id. `{song_id}_*.mp3` can, with the published-version overrides
  (issue #30) as the reverse lookup for produced files.
- **Queue membership cannot tell you where a track came from.** The playlist contains the *current
  song* as well as the queue and `mode="randomize"` can replay it, so a first attempt labelled a
  replayed queue song as "fallback music" — caught on the live stack, not in a test. Each Liquidsoap
  source now tags its own tracks (`metadata.map` → `bigflavor_source`) and the label is the stream's
  answer. Worth generalizing: when the question is "which of my sources did this come from", ask the
  thing that chose.
- **Position is overwritten from `elapsed` every tick**, so drift is structurally impossible rather
  than merely smaller; `elapsed + remaining` gives a length for songs the catalog has no duration for
  (CAT-02), stored beside the song rather than written into it. Nothing compares position against
  duration any more, which is exactly what used to pin a no-duration song on screen forever.
- **A song the stream has started leaves the queue**, so "up next" can't list something already
  played, and the `.m3u` shrinks with the audio rather than with our own count.
- **Silencing `httpx` at INFO was part of the fix, not tidying.** Asking once a second meant one log
  line a second — ~86k a day burying the failures the log exists to surface (PLAT-10). `LOG_LEVEL=DEBUG`
  brings them back.

**`fallback_music` turns out to be unreachable, and that is a pre-existing RAD-02 gap left alone.**
The issue's premise #4 said fallback music plays when the queue drains. It does not: `mksafe(radio_queue)`
is *always* ready, so `fallback([radio_queue, fallback_music, blank()])` always selects the first, and
the logs show every track coming from `radio_m3u`. An empty `.m3u` therefore yields `mksafe`'s
`safe_blank` — silence. Untouched deliberately (the spec puts the fallback source out of scope and
`mksafe` is a documented invariant); the display half handles fallback audio correctly if it ever
plays. Reported on the PR for its own issue.

Verified live: state and stream agreed on song, source label and position (<1s apart) across track
changes; an API skip moved the audio and the page followed in ~4s; Icecast stayed connected
throughout. 38 pytest on the touched files, 206 vitest (+8), lint at zero warnings, build clean. The
two `/api/audio/stream` Range tests in `test_api_routers.py` fail on `main` too — pre-existing, not
touched.

---

### 2026-09-26 — `docs/requirements/`: the product contract the PM now guards
The app's promises were only ever implicit — spread across OKRs, architecture notes, and whatever a
past spec happened to say — so nothing stopped a change from quietly removing a behavior users
depend on. `docs/requirements/` now records them: eight area files (search, radio, agent/DJ, catalog,
production, sessions, accounts, platform) of **MUST** statements with permanent IDs (`SRCH-04`,
`RAD-02`), seeded from what the app actually does today.

- **Requirements ≠ OKRs.** Requirements are invariants ("what must always be true"); OKRs are
  targets ("what we're trying to move"). Keeping them in separate files keeps both readable.
- **IDs are permanent and never reused** — retired requirements stay in the file struck through, so
  a two-year-old issue citing `SRCH-04` still means the same promise.
- **A known gap stays in the file, marked inline** rather than being deleted. Two are recorded:
  the hosted Anthropic path (`PLAT-01`) and the unguarded search/agent routes (`PLAT-03`).
- **The PM authors, the developer commits, QA checks, a human merges.** The PM agent stays
  read-only (it ingests untrusted issue text), so requirement changes ride into `main` inside the
  code's own PR — the merge *is* the approval. Its spec template gained a mandatory
  `**Requirements.**` section: `Honors:` (IDs this change must not break) and `Impact:` (the exact
  new/amended text, ready to paste, or `None`).
- **Conflicts halt for a human.** A greenlit issue that would make a MUST false gets a
  `<!-- pm-agent:requirements-conflict -->` comment, the `requirements-conflict` label, and no
  `dev_ready` — the orchestrator's new **REQ-CONFLICT** bucket parks it above the PM buckets so no
  sweep re-posts it, and it returns to **PM (re-eval)** once a human replies. The gate exists
  precisely to catch "it's obviously fine" reasoning, so there is no obviousness threshold that lets
  an agent skip it.

Touched: `docs/requirements/*` (new), `.claude/agents/product-manager.md` (rewritten around the two
jobs), `.claude/agents/developer.md` (commits the requirement text verbatim),
`.claude/agents/qa-reviewer.md` (contract check in the review), `.claude/commands/fix-issue.md`
(REQ-CONFLICT routing + label), `AGENTS.md`, `.agents/memory/pm_conventions.md`.

---

### 2026-09-25 — Reaper session import: a scanning slice, measured against a real session
First slice of recording-session import (upload a Reaper session zip, find the songs in it). Six new
modules under `src/production/` — `rpp_parser.py`, `wavpack_io.py`, `session_detect.py`,
`session_transcribe.py`, `session_attempts.py`, `session_render.py` — plus `scripts/scan_session.py` as
the diagnostic (`--refine` runs the transcript pass), and 50 pytest tests. Nothing is wired into the API
or UI yet. Validated against the band's own 2 GB session ("20260501 May the Farts Be
With You"), which overturned several assumptions:

- **The audio is WavPack (`.wv`), not WAV.** libsndfile has no WavPack decoder, so `soundfile`/
  `librosa` — and therefore every audio tool here — cannot read session media. ffmpeg 7.1.5 is already
  in the backend image and does, so `wavpack_io.py` is the one module that knows, and everything
  downstream sees the FLAC/WAV it writes. No new dependency.
- **`RECPASS` groups items into recording passes**, so "one press of record" needs no inference.
- **One project file spans many sessions.** The sample's `.RPP` references four passes; two are from a
  different night and point at absolute paths in another project folder whose media is not in the zip.
  Missing media is normal and must be skipped, not treated as corruption.
- **Tracks within a pass do not share a start.** One guitar item sat +81.8s (pass 2) and +144.9s
  (pass 4) after its pass-mates. Aligning by `POSITION` on a shared grid is mandatory; assuming files
  start together would have put that guitar 2.5 minutes out of sync.
- **Half the tracks hold no audio** (automation/MIDI/folder tracks, one at -91 dBFS). The existing
  `instrument_tagging.SILENCE_PEAK` of -40 dBFS separates them from a real -34 dBFS room mic.
- **A band member is called Tom**, so `tom` must not mean "drums" — it mislabelled his vocal and
  instrument tracks. Only the drum spellings (`toms`, `floor/rack tom`) may claim the name.
- **Envelope scanning is cheap**: ffmpeg decodes `.wv` to an 8 kHz envelope at ~1200x realtime, so a
  48-minute 14-track pass scans in 33s.

**Loudness alone cannot find song boundaries, and pulse clarity cannot either.** Detection on the real
pass produced 6 regions, and transcribing them showed two distinct failures: region 1 (8m41s) is the
*same song twice* with two minutes of discussion between, merged because the band keeps noodling while
they talk; region 5 (2m43s) is pure chatter promoted to a take. A tempogram was measured as a refiner
and **scored the talking higher (0.69-0.76) than the song**, because noodling is rhythmic — so acoustic
refinement is out. The transcript is the discriminator, which reorders the pipeline: transcribe the
coarse regions *before* fixing boundaries, then render once. Asking qwen2.5:14b for attempt spans
directly failed (split one attempt in two, called chatter an attempt); asking it to label each
transcript line `lyrics` or `chatter` scored 16/18 zero-shot, both errors isolated single-line flips
inside long lyric runs, which `smooth_labels` removes. Every span decision is arithmetic in Python.

**Then talking turned out not to be the boundary either.** Splitting a region at its chatter cut
"Gardening at Night" in half, because someone shouted "here comes a big solo" over the solo — and a
restart often has no discussion at all, so waiting for talking would miss one. **The band stopping is
the boundary**: they cannot start a song again without having stopped it. `session_attempts.py` now
cuts a region at sustained silences and keeps a span only if somebody sang over it. The stop must be
sustained (`MIN_STOP_SECONDS` = 2.0s) — measured, note gaps inside that solo reached 1.0s while the gap
between two attempts at one song was 5.7s, so the threshold sits in a wide margin. With that rule pass
3 reads as one complete performance, solo included, instead of two half-songs.

**Labelling lines is the weak link, and two things block measuring the alternative.** Batching at 20
lines beat both extremes (86 lines at once degraded badly; one short region alone has no contrast), but
the local 14B still calls 2m43s of "hello hello tv listeners" singing, so that region is offered as two
attempts instead of none. Acceptable for now — import ends in human review precisely because detection
is fallible. Whether a stronger model fixes it is **unmeasured**, because `AnthropicProvider` cannot
make any call at all: `anthropic` 1.7.0 dropped `temperature` from `messages.create` while the provider
always passes it, so `LLM_PROVIDER=anthropic` breaks the agent, DJ and search-explain paths (KR2.3).
The dev `.env` key is also invalid (401). Left unfixed on purpose — shared plumbing on the agent's hot
path deserves its own change, not a drive-by edit inside this slice.

**The feature is now usable end to end** (same day): migration 18 (`recording_sessions`,
`session_tracks`, `session_takes`, `session_take_stems`), `src/api/session_jobs.py`,
`src/api/routers/sessions.py`, BFF routes under `frontend/app/api/produce/sessions/`,
`frontend/lib/sessionUpload.ts`, and the `/produce/sessions` + `/produce/sessions/[id]` pages. Upload
is **chunked** (25 MB pieces, retried at the same `offset` so a retry cannot duplicate bytes and
corrupt the zip) because nginx caps a body at 100 MB; measured 2.03 GB in 14s over loopback. Verified
on the real session: 27 channels parsed across 2 passes (12 live), 9 takes rendered with their stems
and waveforms, raw WavPack purged, 925 MB retained from a 2 GB upload, ~12 minutes end to end.
Frontend is lint-clean, 198 vitest tests pass, `npm run build` succeeds; 60 backend pytest tests.
**There is no catalog import yet** — takes are staged and a producer discards what is not a song; song
grouping and matching are deliberately deferred, which is why there is no `session_songs` table.

One bug the end-to-end run caught that no unit test would have: `Track.peak_db` was an `np.float64`,
so `is_dead` was `np.bool_` and asyncpg rejected it (`invalid input for query argument $8`). `_db()`
now returns a plain `float` and `is_dead` a plain `bool`, with a test asserting the types, because
these values go straight into the database.

Groundwork also landed: `./audio_library/sessions` is a writable mount (the catalog mount is `:ro`),
and `sessions/` + `audio_library/sessions/` are gitignored so a multi-GB zip cannot be committed.

### 2026-09-22 — Released v0.18.0 (kept stems + standalone Separate stems)
Tagged `main` as **v0.18.0** — a minor, not a patch, because PR #95 adds capability that did not
exist before: a save keeps the per-stem audio it just rendered as the new version's stem set, and
**Separate stems** became its own button beside Start analysis. Migration 17 (`song_stem_sets.origin`)
ships with it; **migrations 16 and 17 are already applied to the live database**, so a deployer does
not need to run them. Sanity gate passed (backend booted clean, frontend `npm run build` succeeded).
PR #95 closed no issues, so no issue notifications went out. Production is still on v0.17.3 — this
one is tagged and **waiting on a human deploy**, unlike the previous two releases. PRs #99 and #100
are QA-approved but unmerged and are not in this release.

### 2026-09-21 — A save keeps the stems it just rendered, and separating is its own button
Follow-on from the version-scoping fix: once stems belong to a version, saving fixes produced a
version with *no* stems, so the producer was told to run Demucs on a mix that had just been
assembled from stems — stacking a second generation of separation artifacts on the first.

The parts were already on disk. `_render_mix` writes per-stem audio under
`produced/<song>/accept_fixes/<ms>/` and keeps it; **15 GB across 33 runs**, only 8 of which became
versions, and nothing cleans them up. So the storage was already being spent and simply not used.

- **`remix_inputs` was the missing link.** It is the complete part list for the mix, and the empty-
  chain case makes it so: `_chain_apply_tools` returns its *source path untouched, writing nothing*
  when a stem has no fixes. So fixed stems point at new files and untouched ones at their existing
  stem file — authoritative either way. `_render_mix` now returns it, and `_finalize_save` registers
  it as a stem set against the new version.
- **Every part is copied**, untouched ones included. They arrive pointing at the *previous* set's
  file, and two sets sharing one path is a trap — re-separating or cleaning the older set would
  hollow out the newer one. Costs ~59 MB per stem; a dangling row costs the producer their stems.
- **The render cache had to remember the parts too** (`cached_stems`), exactly as it already
  remembers notices: a save that reuses a warm render never ran the DSP, so without it the stems
  would sit on disk unknown to the request saving them.
- **Migration 17 adds `origin`**: NULL/'separated' for Demucs, `'fixes'`, or `'fixes_premaster'`
  when master-scoped fixes ran after the remix — those stems sum to the pre-master mix, not the
  saved file, and saying so beats letting a producer wonder why the parts don't add up.
- **Keeping is best-effort and cannot fail a save.** Found the hard way: `save_candidate_version`
  returns `{"version_id": …}`, not `{"id": …}`, and my `version["id"]` raised *outside* the helper's
  try — turning a good save into a 500 and leaving an orphan version row. The call is guarded now.

**Separate stems** moved out of the console and next to Start analysis, renamed, and is now its own
action (`separateStems`, with its own `separating` flag) rather than always dragging a measuring
pass behind it. A version with no stems can be separated and simply looked at.

**Worth knowing for later:** `song_stem_sets.source_version_id` is **ON DELETE SET NULL**, so
deleting a version orphans its kept stems — invisible under version scoping, and ~350 MB a time.
That interaction is now live and unhandled.
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

### 2026-09-21 — Stems belonged to the song; they belong to a version (song 1144)
Reported from production: a popping sound audible in song 1144's *cleaned* mix could not be found
in any stem. It wasn't a hearing problem — the stems were the **original's**.

Song 1144 had two versions (75 original, 76 cleaned) and exactly one stem set, `source_version_id`
= 75. `latestComplete()` picked the song's newest complete set and **never looked at
`source_version_id`**, even though the field was fetched and sat on the row. Meanwhile the full-mix
console row is built from `/api/produce/versions/{sourceVersionId}/…`, so it *did* follow the
selection. That split is the whole symptom: the artifact was in the mix row and in none of the stems
below it, because they were a different recording.

- **Worse than a display bug.** `waitForStemSet(forceNew=false)` used the same function, so Start
  analysis on the cleaned version *reused the original's stems* and filed the measurements against
  the version selected. Every per-stem fix accepted was computed from audio nobody was listening to.
- The root cause was written down in prose and believed: a comment read *"Stems are not cleared:
  they belong to the song, not to a version."* That is the defect, stated as intent. Stems now clear
  and refetch on a version change like fixes do.
- **Four call sites** inherited it (mount preload, tag poll, Start analysis reuse, rename fallback),
  plus the separation wait loop and its already-running guard, which watched the song's newest set
  rather than this version's.
- **The cost is honest and real:** selecting a version nothing has been separated from now means a
  Demucs run. The alternative is measuring another version's audio, so there isn't a cheaper correct
  option. The empty state says *why* the stems vanished (`stemsOnAnotherVersion`), because otherwise
  switching version just empties the console and reads as a fault.
- **Migration 16** backfills legacy `source_version_id IS NULL` sets (added before the column) to the
  song's `original` version — provably the file those runs used, since a null request resolves to the
  catalog original. Only where exactly one original exists; anything ambiguous stays null and is
  re-separated rather than guessed. Applied: 4 rows on song 1650, re-run is `UPDATE 0`.

Also fixed here: `__tests__/ResultSidebar.test.tsx` had two mocks left behind by PR #92's prop
retyping. `next build` does not typecheck test files, so `npm run build` was green while
`tsc --noEmit` was red on main — worth remembering that the build gate alone does not cover tests.

The three new hook tests were confirmed **red against the old selector** before being kept, and
`--max-warnings=0` again caught two stale dependency arrays (the tag poll would have merged tags
from the wrong version's set after a switch).

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

### 2026-09-21 — The pitch gate was two scopes wearing one constant (issue #91)
#89 moved the monophony thresholds into shared constants so the tool "cannot recommend a correction
it would then decline to make". It still could. `analyze()` measured the loudest 20 s window at
22.05 kHz; `apply()` re-derived the same two numbers over the **whole file at native rate**. Sharing
the numbers is not sharing the measurement.

**Measured before choosing anything** — 66 stems, 10 songs, every separated set in the catalog, via
the shipping functions rather than a re-implementation:
- **6 of the 15 recommended stems were refused by the render.** The producer accepted a card with
  numbers on it, waited, and got their audio back unchanged.
- The issue guessed it was `PITCH_MIN_VOICED_RATIO`. Half right: **3 of the 6 failed on
  *confidence*** instead, and those three basses passed the file-wide ratio comfortably. Both
  constants had the scope problem.
- **Option 1 (a separately calibrated file-wide constant) is dead on the numbers.** The loosest pair
  that removes all 6 contradictions is ratio 0.25 / confidence 0.07 — which admits **33 of 66
  stems**, drums and near-silent stems included. That is the gate switched off, not calibrated. And
  no offset could be calibrated away anyway: the per-stem gap between the two scopes ran **-0.43 to
  +0.69**.
- **Scope alone was not enough either.** Gating on apply()'s own native-rate f0, windowed, still left
  two bass stems refused — pyin's confidence moves with sample rate on low sources (0.14 at 44.1 kHz
  vs 0.29 at 22.05 kHz). Rate is part of the measurement, not an implementation detail.

So: **one shared measurement**, `measure_monophony()` + `passes_monophony_gate()`, called by both
halves. Contradictions **6 → 0** across all 66 stems; per-note eligibility *rose* **12 → 22** rather
than collapsing. Verified end-to-end by running the real analyze → apply path on the 6 former
failures: all now correct per-note (284-684 notes each), and drums / a polyphonic guitar still
refuse. Bonus: the gate runs *before* apply()'s full-length pyin, so a refusal went from ~12 s to
~2-4 s.

**The test asserts the property, not a number** — recommended ⇒ per-note-runnable — because the
property is what kept breaking, and a threshold test would have passed through both versions of this
bug. It carries a guard-the-guard case asserting its own fixture still reproduces the scope gap, so
it cannot quietly stop covering anything. Checked it fails against the old code before keeping it.

**A second, quieter half:** `_chain_apply_tools` read tool results only for `status`, so
`fallback_reason` had **no route to the UI at all** — the silent-unchanged-audio outcome was
unreportable by construction. Chains now return notices, stored with the *render* (Start analysis
warm-renders nearly everything, so a reused render must be as honest as a fresh one). And
`isPitchAnalyzable` read only `instruments[0]`, so a fiddle tagged second inside `other` was skipped
though the comment claimed otherwise; it reads all tags now.

**Where a notice is shown turned out to be the whole trick** (QA round 2). Reading notices off the
response to "Accept all & save" works only for a cache hit: a fresh save is a background job, and
`accept_jobs.start()` seeds the dict `"notices": []`, so the panel rendered empty — on exactly the
case that raises notices, since hand-adding a `correct_pitch` card changes the fingerprint and
therefore always misses the warm render. Moving the read to the status poll is necessary but not
sufficient: the poll that completes a save selects the new version, which **clears the fix queue and
unmounts the sidebar the notice was being rendered in**. So a save reports on the *page* (under the
versions table, via a shared `FixNoticePanel`), and only a preview — which waits for its own render
— reports in `ResultSidebar`. `useAcceptJob` holds the notices across the dismiss that same poll
performs, and drops them when the next render starts. Worth remembering generally: in this console,
a save deliberately throws away the queue that started it, so anything a save has to say has to
outlive it.

Backend boots, 38 pytest green on the touched files, 164 vitest (+9), lint at zero warnings, build
clean. `tests/test_editing_tools.py` fails on `input()` — pre-existing, one of the ad-hoc scripts
TESTING.md documents. Still not seen on screen: the produce console is behind an editor Google
session, so the notice panel is covered by component tests and types rather than by eyes.

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

### 2026-09-19 — Pitch and clicks are measured now, and a fix is auditioned in the mix (issue #89)
Two halves of the same idea: a fix you can only find by ear isn't leverage, and a fix you can only
hear as an isolated clip can't be judged.

**Detection.** `correct_pitch` and `remove_artifacts` had inherited the base `analyze()` stub, so
nothing could ever recommend them. Both detections already ran inside `apply()`; what was missing
was running them without the write. `detect_pitch_issues()` / `detect_clicks()` now live in
`analysis.py` beside `detect_hum()`, shared by the two tools and by the whole-song recommender.

- **The apply-side click rule could not be reused.** `apply()` cuts at
  `percentile(100 - sensitivity * 20)` — at the declared 0.5 that is the top *10% of every file*, by
  construction, so it can never say whether a file is clean. `analyze()` uses an absolute outlier
  rule instead (a jump ≥8x the track's own 99th-percentile jump, grouped into events) and then maps
  its measured flagged fraction back onto a `sensitivity`. On a real Demucs
  `other` stem: 41 clicks, 9.9/min, sensitivity 0.005 — not 0.5. **But that fixes detection only,
  and QA was right to press on the wording:** `sensitivity` is a percentile of the whole file
  whatever you pass it, and the recommendation almost always lands on its floor
  (`CLICK_MIN_SENSITIVITY = 0.005` → `percentile(99.9)`). Measured on that same stem: 10,927
  samples over the threshold and **78,597** once apply()'s 1 ms kernel widens them — 0.7% of the
  channel, to repair 41 events — plus an unconditional savgol pass over the whole channel. Read a recommended card as *the gentlest setting this param has*, not "repairs
  what was measured". A genuinely targeted repair needs `apply()` to take sample **positions**
  rather than a threshold; `apply()` is left alone and that is the follow-up.
- **The monophony gate had to move, and that was the real find.** `apply()` refused any source
  voicing under 0.5 mean pyin confidence. Measured across four songs, *every* real vocal stem sits
  at 0.21-0.24 — pyin's `voiced_prob` comes out of Viterbi-decoded candidates and is nowhere near
  1.0 even on a clean solo line. So per-note auto-tune had **never once run on a stem**; it silently
  fell through to a whole-file shift every time. The constants moved to `analysis.py` (ratio 0.6,
  confidence 0.18) and `apply()` reads them, so the tool cannot recommend what it would refuse.
  Polyphonic stems that voice just as often (`other`, `guitar`) sit at 0.05-0.17, and the off-target
  ratio is a second gate they also fail (0-5% against a vocal's 15-70%).
- **Deviation is scored against the nearest semitone, not the nearest in-scale note.** "Flat" means
  off its own pitch; scoring against the key counts every deliberate chromatic note as an error. The
  key is still detected and shipped as the recommended `key` param. 35 cents is the line — at 25
  cents all four test vocals tripped it, which is just normal expressive singing. **QA caught the
  other half of this:** the recommended params left `chromatic` at its default `false`, so `apply()`
  aimed at the in-scale tone while `analyze()` scored against the semitone — on a real vocal stem
  that moved 43 of 46 notes, 6 of them notes the card had just counted as in tune. `chromatic: true`
  now ships with the recommendation. Measure and repair have to aim at the same target; it is not
  enough for each half to be defensible on its own.
- **Cost, the risk the issue called out:** pyin over a whole stem would have been ruinous, so it runs
  on the loudest 20s window at 22.05 kHz, and only on rows where a single line is plausible
  (`isPitchAnalyzable`: the vocal stem, or a tagger-labelled single-line instrument — never the full
  mix). Measured on a real 6-stem set: 17.9s → 25.5s of serial analyze CPU, 1.43x.
- **`match_tempo` stays un-recommended on purpose** — there is no correct BPM for a song. It just
  gets seeded: the analyze helpers now keep *every* outcome, not only recommended ones, so
  `correct_beats`' `detected_bpm` (which it reports either way) pre-fills the one required param in
  the registry and the card is runnable on arrival.

**Auditioning.** Hear it drove a per-card `<audio>` element, so you heard the fix alone, through a
player that knew nothing about the rest of the mix. It now drives the console's single transport —
which already rendered per-row fix chains on demand, so this was rewiring, not new machinery. Hear
it selects the row, turns the fix on and plays; ON/OFF while auditioning re-renders and resumes at
the same playhead. Keyed on *which* fixes are enabled rather than their params, so the Adjust
drawer's sliders can't kick off a render per keystroke. `previewSingleFix` deleted.

14 new pytest cases, 20 new vitest (155 total green), lint/tsc/build clean, backend boots.
Two of those pytest cases came out of the QA round: one pins the recommended params to the
same snap target the deviation is measured against, the other pins the sensitivity floor and
says in its name that the floor is what it is testing.

---

### 2026-09-18 — Every DSP tool is addable by hand, not just the four with detectors
Asked why the picker offered only 4 options. Traced it: `PER_STEM_TOOLS`/`MASTER_TOOLS` were the
*analysis* lists — tools with a real `analyze()` — and the manual picker had been built from them.
Three genuinely useful tools were invisible as a result, and checking where they were reachable at
all turned up nothing: **`correct_pitch`, `remove_artifacts` and `match_tempo` had no route through
the produce UI whatsoever.** `correct_pitch` is mapped in `region_tools.py` but no component calls
`/api/produce/region/*` (the BFF handlers have no caller); `correct_pitch`/`match_tempo` are
`auto_clean` steps 4b/4c behind `do_pitch`/`do_tempo`, which no UI passes; `remove_artifacts` is in
neither. Agent chat was the only way to run any of them.

And the analyzer can never surface them: `analyze_and_recommend_processing` reports on
trim/hum/noise/eq/compression/mastering only, and those three inherit the base `analyze()` stub that
always says `recommended: false`. So the picker isn't a convenience for them — it's the only door.

- **The picker now comes from the registry**, not a list: every non-hidden `applies_to_file` tool,
  minus an `ADDABLE_SCOPE` table of exceptions justified by the audio (`trim_silence` changes
  length; `apply_mastering`/`normalize_audio` are mix-bus jobs). 7 tools on a stem row, 10 on the
  full mix, and a new backend tool shows up with no frontend change.
- **`match_tempo` needed a guard, not just a listing.** `target_bpm` is `required=True` — the only
  scoped param that is — and `coerce_args` *raises* rather than defaulting, so a card at defaults
  would have failed the render instead of quietly doing nothing. `missingRequiredParams` reads the
  `required` flag the descriptor already carried (no backend change), the card reads SET UP and says
  what it needs, and `isRunnable` holds it out of every chain until it has a value.
- **`correct_pitch` at its declared defaults is an exact no-op** (`semitones: 0`, `auto_tune: false`)
  — the `remove_hum` problem again. A hand-added card starts with `auto_tune: true`, which is what
  someone reaching for it wants.
- **Adding it exposed a drawer bug:** a declared `string` param with no `choices` fell through to the
  number input, so `correct_pitch`'s `key` ("C", "A minor") could not be typed into. The drawer has a
  text branch now, marks required params, and an emptied number field means *unset* rather than 0.
- On a stem, `match_tempo` stretches that stem alone; the card says so, since the set drifts apart
  unless every stem gets the same target.

**The lint gate earned itself back the same day:** `--max-warnings=0` caught `isRunnable` missing
from two `useCallback` dep arrays — a stale-closure bug that would have built chains from an
outdated completeness set. 8 new vitest cases (135 total green), lint/tsc/build clean.

---

### 2026-09-18 — The fix queue can now hold a fix the analysis never measured (issue #86)
The review queue only ever showed what `analyze()` flagged, so a producer who could *hear* something
below the detector's threshold had no route to it in that screen. The fix turned out to be entirely
frontend: `/accept-fixes`, `/stems/{id}/preview-chain` and `_chain_apply_tools` take an arbitrary
`{tool, params}` list with **no tool whitelist**, and `accept_jobs.fingerprint` hashes the whole
payload — so a producer-chosen card reaches the DSP, renders, and invalidates a stale render
without a line of backend change. Checked that before designing anything.

- **`FixEntry.source: 'analysis' | 'manual'`** is the whole model change. Everything downstream reads
  `tool` + `currentParams` and never asks where a card came from, which is why Hear it, Adjust,
  ON/OFF and Accept & save all worked for free.
- **Ids stay `stem:<id>:<tool>` / `master:<tool>`.** The issue flagged a possible collision; keeping
  the existing scheme makes a duplicate structurally impossible instead of something to reconcile —
  the picker just hides tools the row already has.
- **Re-analysis merges rather than replaces.** Manual cards survive (clearing them would make the
  producer's own judgement the one thing a re-measure throws away); where the new pass recommends a
  tool they had added, the recommended card wins and inherits the params they had moved off the
  suggested value. "Edited" is *derived* (`currentParams` vs `suggestedParams`) rather than tracked,
  so there's no second copy of the params to keep in sync. A re-separation drops manual cards pinned
  to stem ids that no longer exist.
- **Starting params are the tool's declared defaults**, minus `file_path`/`output_path` and
  `start_s`/`end_s`. Worth knowing: `apply_eq`'s defaults alone are close to a no-op (high-pass at
  30 Hz, no `boost_freq`), which is exactly why the Adjust drawer is the place the amount gets set —
  there are no measured numbers to pre-fill.
- `ensureToolParams` now keeps the whole tool descriptor (`summary`, `applies_to_file`,
  `hidden_from_editor`) rather than just params; `toolParamsByTool` is derived from it, so the
  Advanced drawer's call sites didn't change.

**QA follow-ups, same PR.** The picker now labels each option with `fixTitleFor(tool)` — the very
title the card it creates will carry — instead of the tool's own `summary`, so "Even out the tone"
doesn't produce a card called something else (the summary is the option's hover text).
`manualFixCopy` calls the same helper. And `remove_hum` gets its own card copy: it is the one scoped
tool whose declared defaults are a genuine no-op (`fundamental_hz` has no default, so apply re-runs
the detection that already found nothing and copies the file), so the card says to pick 50 or 60 Hz
under Adjust rather than leaving "Hear it" sounding broken.

16 vitest cases across two specs (127 total green), `tsc --noEmit`, `npm run build` and — newly —
`npm run lint` all clean.

---

### 2026-09-18 — Linting works again: flat ESLint config, repo clean at zero problems
`npm run lint` had been dead since the Next 16 upgrade: `next lint` was removed, so the script read
`lint` as a *directory* argument and errored out. Every frontend PR had been shipping with the lint
gate declared broken. Now `"lint": "eslint ."` against a flat `frontend/eslint.config.mjs`
(ESLint 9; `eslint-config-next/core-web-vitals` + `/typescript` both ship flat-config arrays, spread
in as-is). `.eslintrc.json` is gone — ESLint 9 ignores it anyway.

Turning it on surfaced 11 real errors, all fixed rather than configured away:
- Six `no-html-link-for-pages`: in-app `<a href="/">` "Back to Home" links became `<Link>` (they were
  doing full page reloads). The two in `UserButton` are **not** bugs — `/api/auth/login|logout` are
  route handlers that server-redirect to Google, which `next/link` cannot do — so those carry a
  targeted `eslint-disable-next-line` **with the reason written out**.
- Three unused vars: two bare `catch {}` in `SongList`, one dead `const user` in the radio page.
- Two `react-hooks/set-state-in-effect` (new in eslint-plugin-react-hooks 7) in `AudioPlayer`, both
  genuine improvements once fixed: `isPlaying` now follows the element's own `play`/`pause` events
  instead of our call (correct when autoplay is refused or the OS media keys drive it), and timed
  lyrics are stored as `{songId, timings}` and *derived*, so switching songs shows no lyrics rather
  than the previous song's until the fetch lands.

Two config-level choices worth keeping: `@typescript-eslint/no-explicit-any` is **off** (the
produce/audio layer passes tool params as open-shaped records because the backend registry declares
their shape at runtime), and `no-unused-vars` ignores *arguments* but still errors on locals.

The repo now lints at **zero errors and zero warnings**, which is the point — output means your
change. `.agents/TESTING.md` updated accordingly.

---

### 2026-09-16 — Every audio tool ran on the event loop, freezing the whole API
Found while checking that the new in-progress row appeared: page loads during a
render were taking a minute. The frontend log said it plainly —
`GET /api/produce/songs/1004/versions 200 in 60s`, a plain DB read, while an
accept-fixes render ran.

`BigFlavorMCPServer.dispatch_tool` did `await handler(**kwargs)`. The handlers
are `async def` but their bodies are **synchronous** librosa/soundfile work with
no awaits of their own (7 awaits in the whole module, none in a DSP handler), so
minutes of CPU ran directly on the loop and every other request queued behind it.
Pre-existing — the synchronous accept path had the same problem — but the
background render made it constant instead of once per deliberate click.

Fix is one line: `await asyncio.to_thread(asyncio.run, handler(**kwargs))`. Safe
because the handlers touch only files, never the loop-bound asyncpg pool.
Measured during a 12-fix render: `/health` and `/versions` went from **60s** to
**0.01-0.56s**.

**Moving work to a background task does not help if the task blocks the loop** —
worth checking before calling any long job "backgrounded".

Also in this pass: the rendered-but-unsaved mix keeps a selectable row in the
versions list so it can be A/B'd against the original before saving
(`lib/unsavedRender.ts`, `UNSAVED_VERSION_ID = -1`), which is why
`RESULT_TTL_SECONDS` went from 15 minutes to 8 hours — and why the TTL test now
pins itself to that constant rather than hardcoding an hour.

---

### 2026-09-16 — "Save the version" was re-doing all the DSP, twice
A 17-fix queue 504'd on save and the UI suggested turning fixes off. Asked why
saving was slow at all — surely the processing was done? Checked: it was not.
**Analyze measures and never renders** (its own docstring: "findings +
recommended params, no processing"), so every fix was still unrendered when a
button was pressed. `_chain_apply_tools` then runs each tool for real, writing a
WAV per step, per stem, then remix, then master. Stems *are* reused — that part
of the instinct was right.

Worse: "Preview full mix first" rendered exactly that, and saving threw it away
and rendered it again. And a version row is just a path — `add_song_version`
stores `audio_path`, it never copies audio — so saving an already-rendered mix
should be an insert.

So the fix was not only "run it in the background":
- **Start analysis now renders what it detected** (`warmRender`), because the
  reason to analyse is to hear or keep the result. Preview and Save then land on
  a finished file.
- **A fingerprint over source version + every fix and its params** decides reuse.
  It deliberately excludes `preview`, since preview and save produce identical
  audio — that exclusion is what lets the analysis render satisfy a later save.
  Measured: cold render 17.6s, same-fixes save 0.94s (`reused: true`), changed
  params correctly re-rendered at 18.6s.
- **`AcceptJobManager`** mirrors `stem_jobs.py`; status is in memory because the
  result is durable. `useAcceptJob` polls **on mount**, so a reload mid-render
  resumes, shows an in-progress row in the versions list, and reloads the list
  when a save lands.

**Verification gotcha worth keeping:** starting a render server-side while the
page sits idle proves nothing — the page polls on mount and then only while
running, so a render begun elsewhere after load is invisible by design. Start
the render *first*, then navigate. Also, a render saturates the CPU enough that
the dev server's own page load crawls; wait for `tbody tr` to exist rather than
a fixed sleep.
