# Produce / Stem Console — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) on 2026-09-14 to keep the rolling file under ~200 lines.
These are the entries that built the `/produce` per-tool API and the stem console UI, newest first.

---

*The seven 2026-09-16 → 2026-09-21 entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-09-27 prune.*

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

---


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

---

## Later entries (moved from MEMORY.md, 2026-09-18)

### 2026-08-06 — "Start analysis" never re-separates over existing stems (now stated, and tested)
The rule the produce tab runs on: **Start analysis separates only when the song has no usable stems;
making new ones is Re-separate's job.** `useProcessingQueue.waitForStemSet(forceNew)` already
implemented it — `forceNew=false` returns `latestComplete(sets)` and never POSTs
`/api/produce/stems/separate` — but nothing said so, and three bits of UI copy promised that Start
analysis "separates the song into stems" regardless. The copy in `VersionBar` now switches on
`hasStems` ("measures the stems you already have · use Re-separate below to make new ones") and the
`/produce/[songId]` blurb says separation is the first-time path.

The load-bearing part is `frontend/__tests__/useProcessingQueue.test.ts` — the first hook test in the
repo, and the thing that stops a future edit from quietly reintroducing a multi-minute Demucs run on
every press. Two testing notes for anything else that exercises this hook:
- **Don't use RTL `waitFor` with `vi.useFakeTimers()`** — it polls on an interval the fake clock
  freezes, so every assertion hangs to the 5 s test timeout. Await the pass inside `act()` and assert
  directly; drive the hook's 4 s separation poll with `vi.advanceTimersByTimeAsync()`.
- Give fake stems `tagged: true`, or the background instrument-tag poll keeps firing through the test.

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
