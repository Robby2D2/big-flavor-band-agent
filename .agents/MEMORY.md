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
