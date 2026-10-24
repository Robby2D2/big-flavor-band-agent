# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-10-24 (207 lines → ~150): the 2026-10-15 entries moved — the production-frontend
> deploy fix to [memory/deploy_ops.md](memory/deploy_ops.md); lyric search ranking and the PyAV pin
> to [memory/search_rag.md](memory/search_rag.md); radio lyrics, real pause and the listener count to
> [memory/radio_streaming.md](memory/radio_streaming.md).
>
> Pruned 2026-10-15 (556 lines → 129): the 2026-09-26 → 2026-09-28 entries moved to their topic
> files — radio #101/#104 to [memory/radio_streaming.md](memory/radio_streaming.md); session
> import, grouping and review to [memory/sessions_import.md](memory/sessions_import.md); playback
> warming and the render/task panel to [memory/produce_console.md](memory/produce_console.md);
> issues #111 and #114 to [memory/search_rag.md](memory/search_rag.md); the #107 indexing gap to
> [memory/scraping.md](memory/scraping.md); v0.20.0 to [memory/releases.md](memory/releases.md).
> What stays is the 2026-10-15 work and the `docs/requirements/` contract. Earlier prunes
> (2026-08-01 → 2026-09-27) are recorded in [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md)'s table.

---

### 2026-10-24 — Drive import takes nights that are plain mp3s, not Reaper projects (SESS-21)

The owner's "20261023 - Freeish Birdish" folder (two room mp3s, no `.RPP`) never appeared under
Import from Drive, because a session was defined as "a folder that directly holds a `.RPP`". A
folder of plain recordings (`RECORDING_SUFFIXES`: mp3/m4a/aac/wav/flac/ogg — **not** `.wv`) now
counts too, **unless a project folder encloses it**: inside a project, a folder of audio is that
project's "Audio/" or rendered mixes. With no `.RPP`, `session_jobs.load_project` builds a stand-in
(`rpp_parser.project_from_recordings`): each file is its own pass holding one `MIXDOWN` item, scanned
as role `mix`, which counts as rhythm (it is the only track) and as a voice (Whisper hears the whole
mix). Mixdown takes register **no stems**, so a produced version can still be Demucs-separated.
Zip uploads of mp3s work through the same path.

- **The per-track floor rule found nothing on a real mp3.** `freeish.mp3` is heavily limited
  (median RMS −4.7 dBFS), so its 20th percentile *is* the band and "floor + 9 dB" sat above 0 dBFS:
  zero regions. A mixdown is now "playing" within `MIX_DROP_DB = 12` of its 90th-percentile level,
  measured on both files (10 split off an 8s scrap, 15 let talking in). Two files is a tuning.
- What the real files hold: `freeish` is one ~25 min stretch of continuous playing (0:18–25:54);
  `CanadaMan` is 1h46m of which only the first ~24 min has audio — 0:00–1:55 and 7:35–23:18, the
  rest ~−57 dBFS. Expect long takes; the band was not stopping between songs.
- **Verified:** detection on the real files via `docker exec` (no DB writes); the Drive listing now
  shows 34 sessions (was 33) with no project "Audio/"/"Renders" folders listed; 123 session/Drive
  pytest tests. **Not verified:** a full import (Whisper on a full-band mix, take rendering, review
  page) — it writes to the live DB and was left for the owner to run.

---

### 2026-10-23 — Lyric extraction drops Whisper's phantom lines; produce page gets follow-along

Song 2304 came back as "Thank you." ×7 and, from a 4-stem mix, "© transcript Emily Beynon" ×10 —
Whisper's training-subtitle sign-offs, emitted over instrumental audio at *high* confidence, so the
0.5 floor never caught them. `transcribe_audio()` now drops whole-segment phantoms
(`is_phantom_segment()`, `tests/test_lyrics_phantoms.py`) and runs with
`condition_on_previous_text=False`, which on 2304's vocal stem recovered the whole missing first
verse and stopped a line repeating through a break. Tried and rejected: `vad_filter` (kills the
phantoms but merges lines into 30–50s segments — useless for follow-along) and
`hallucination_silence_threshold` (no change). An all-phantom transcript is now empty → "No lyrics
detected" → the job fails and the saved lyrics survive. Same day, follow-up: `transcribe_audio()`
peak-normalizes to -1 dBFS before Whisper (`_peak_normalized()`) — 2304's original vocal stem peaked
at 0.29 and lost whole verses (8 lines → 23 once normalized) — and the API job's confidence floor
dropped 0.5 → 0.4 (real lines scored 0.47). Catalog songs always extract from the *original's* stem
set, not the default cleaned version's (`_default_source_version_id` is None for them). The produce `TransportBar` got a **Lyrics**
toggle that refetches `/api/songs/{id}/lyrics/timed` on each open and runs `LyricsFollower` off the
stem playhead.

### 2026-10-21 — Vocal fixes: pitch correction stops clicking, click removal stops muffling

`correct_pitch` per-note mode hard-pasted each shifted note over the original (`out[s:e] =
pitch_shift(...)`): a waveform step, so a click at both edges of every corrected note. Measured on
song 2304's vocal stem: 72 notes shifted in 20s → 32 new clicks. `_splice_shifted_note()` now
shifts each note with one STFT frame (2048 samples) of real context and crops it back, then blends
it in over 10ms raised-cosine fades (gains sum to 1, because shifted and original audio are nearly
identical) inside the note's own span. Same clip → 0 new clicks. Regression test:
`test_corrected_notes_are_spliced_in_without_clicks` (fails on the old code: jump 0.53 vs 0.16).

**Click removal repairs only the clicks.** `remove_artifacts.apply()` used to interpolate over the
top-N% of every file's jumps, then Savitzky-Golay the whole channel. On the 2304 vocal that kept
1% (sensitivity 0.5) to 7% (the old 0.005 floor) of the high end. Now `analysis.find_clicks()` is
shared by `detect_clicks` and `apply()`, and `repair_clicks()` rebuilds only the flagged spans by
forward/backward linear prediction. `sensitivity` → `click_ratio()` (0.5 = 8x = what the card
counts). `CLICK_MIN_SENSITIVITY` is gone. 2304 vocal stem: 0.14% of samples changed, 86% of HF
kept, 2.8s for 4.5 min. Its remaining "clicks" are 35-140 ms bursts (>20 ms, skipped on purpose)
that are in the original MP3 too.

### 2026-10-19 — Fix ON/OFF is an instant A/B (PROD-21)

Toggling a fix used to wait on a server render of the new chain. Then it did a full stop and
restart (`play(from)`), because the console held only one take per row (`fixedBuffers`). Now:
- `AudioProcessingTab` keeps a `takes` Map keyed `takeKey(row, chainSignature)` (`lib/fixTakes.ts`).
  It is LRU-capped at `MAX_TAKES = 10`, never evicts a take that is playing, and is cleared when the
  version changes (the full-mix row is id -1 on every version).
- `loadTake()` dedups in-flight renders, so a toggle onto a take that is already pre-rendering joins it.
- After `NEIGHBOUR_DELAY_MS`, the selected row's one-toggle-away chains (`neighbourChains`) render
  one at a time. This doesn't run while the whole-queue render does. `previewStemChain(stemId, chain?)`
  now takes an explicit chain.
- `useStemPlayback` swaps a row whose buffer changes mid-play in place. The new source starts at the
  same offset on the same clock, with a 15 ms crossfade (`Voice` = src → fade → row gain). End of
  song is detected by the rAF tick, not `onended` (a swap stops sources early). Callers no longer
  re-`play()` to pick up a landed render.

---

### 2026-10-16 — Lyric extraction picks its vocal tracks (PROD-20)

Lyric extraction used `get_vocals_stem_path()` (now removed). It had two bugs:
1. **Wrong mic.** It matched `st.name = 'vocals'` exactly. A session take names its stems by role
   in track order (`vocals`, `vocals-2`, …, `session_render._unique_name`), so only the *first*
   vocal mic was ever transcribed. On 1000001/1000002 that was "4 Kev Vox" (harmonica/accordion).
   "8 Tom Vox", the actual singer, was ignored.
2. **Wrong take.** It took the newest complete stem set of *any* version. Song 1000001's newest set
   (48) belongs to version 104, while the audio being transcribed is the published version 95
   (set 39), so the timings wouldn't line up with what plays.

Now `lyrics_jobs.find_lyrics_stem_set()` takes the newest complete set whose `source_version_id`
matches the version being transcribed. That version comes from the router's new
`_default_source_version_id()`, which is also used by `_resolve_clean_source_path`. A catalog song
(version None) falls back to its newest set. By default, every stem with "vocal" in `name` or
`display_name` is used (`is_vocal_stem`); several stems are summed with
`session_render.mix_audio_files` before Whisper. New `GET .../lyrics/vocal-tracks` lists the set's
stems with `default` flags. `POST .../lyrics/extract` takes an optional `{stem_ids}`: omitted means
the defaults, `[]` means the full mix via Demucs, and ids outside the set get a 400. LyricsPanel has
a "From: …" multi-select dropdown next to Re-extract.

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
