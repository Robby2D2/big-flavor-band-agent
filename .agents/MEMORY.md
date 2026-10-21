# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-10-15 (556 lines → 129): the 2026-09-26 → 2026-09-28 entries moved to their topic
> files — radio #101/#104 to [memory/radio_streaming.md](memory/radio_streaming.md); session
> import, grouping and review to [memory/sessions_import.md](memory/sessions_import.md); playback
> warming and the render/task panel to [memory/produce_console.md](memory/produce_console.md);
> issues #111 and #114 to [memory/search_rag.md](memory/search_rag.md); the #107 indexing gap to
> [memory/scraping.md](memory/scraping.md); v0.20.0 to [memory/releases.md](memory/releases.md).
> What stays is the 2026-10-15 work and the `docs/requirements/` contract. Earlier prunes
> (2026-08-01 → 2026-09-27) are recorded in [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md)'s table.

---

### 2026-10-21 — Pitch correction no longer clicks at note edges

`correct_pitch` per-note mode hard-pasted each shifted note over the original (`out[s:e] =
pitch_shift(...)`): a waveform step, so a click at both edges of every corrected note. Measured on
song 2304's vocal stem: 72 notes shifted in 20s → 32 new clicks. `_splice_shifted_note()` now
shifts each note with one STFT frame (2048 samples) of real context and crops it back, then blends
it in over 10ms raised-cosine fades (gains sum to 1, because shifted and original audio are nearly
identical) inside the note's own span. Same clip → 0 new clicks. Regression test:
`test_corrected_notes_are_spliced_in_without_clicks` (fails on the old code: jump 0.53 vs 0.16).
Open finding, not fixed: `remove_artifacts.apply()` interpolates over the top-N% derivative samples
and then Savitzky-Golays the *whole* channel. On a vocal it keeps 1% (sensitivity 0.5) to 7% (the
floor) of high-frequency energy, so it muffles without adding clicks.

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

### 2026-10-15 — Production deploy actually runs the production frontend

`deploy-production.ps1`/`.sh` used the plain `docker-compose.yml`, which is the hot-reload dev stack:
the frontend ran `next dev` from `Dockerfile.frontend.dev`, so bigflavor.useunix.com showed the
Next.js dev-tools "N" badge to every visitor and compiled pages on demand. New
`docker-compose.prod.yml` override (frontend → `Dockerfile.frontend` standalone build, `NODE_ENV=production`,
`volumes: !reset []`; backend `APP_ENV=production`); both deploy scripts pass `-f docker-compose.yml
-f docker-compose.prod.yml` on every compose call. Consequence: in production, frontend edits need a
redeploy (image rebuild) to go live, and a bare `docker-compose up -d` flips the frontend back to dev.

---

### 2026-10-15 — Lyric search ranks by relevance, not alphabetically

In-depth search for "down by the river" missed most versions of that song. `search_lyrics_by_keyword`
sorted `ORDER BY title` before its `LIMIT`, so a common word ("river" — 58 songs) filled the 25 slots
with whatever sorted early (ten takes of "25th of December"). It now orders by title-contains-keyword,
then keyword occurrences in the lyrics, then title. Still open: the deep-search planner never chose
`find_song_by_title` for a title-shaped query, and the qwen evaluator dropped title matches the
semantic search had found.

---

### 2026-10-15 — Lyric extraction broke on PyAV 19; `av<19` pinned

Every "Re-extract from audio" failed with `open() got an unexpected keyword argument
'metadata_errors'`. `av` was unpinned (a faster-whisper transitive dep), a rebuild pulled PyAV 19.0.1,
which removed that kwarg, and faster-whisper 1.2.1's `decode_audio` still passes it. The extractor
catches the exception and returns it as `result["error"]`, so the log shows only the message — run
`faster_whisper.audio.decode_audio(<file>)` in the container for the real traceback. Pinned `av<19` in
`requirements-api.txt` and `setup/requirements.txt`; drop the pin once faster-whisper stops passing
`metadata_errors`.

---

### 2026-10-15 — The radio page shows the on-air song's lyrics

- A **Lyrics** toggle in Now Playing opens `components/RadioLyrics.tsx`, which reads the existing
  listener-scoped `/api/songs/{id}/lyrics/timed` and reuses `LyricsFollower` when timings are
  followable; otherwise it shows the plain text, or "No lyrics for this song." No backend change.
- The radio has no local clock, only the 3 s polled `position`: `RadioLyrics` re-anchors on each
  poll and runs the clock forward with rAF between polls (held while `is_playing` is false). Lines
  are not seekable — the stream is shared (RAD-01). The polled position is the server's, so the
  highlight can run a few seconds ahead of what a listener hears through Icecast's buffer.
- Tests: `frontend/__tests__/RadioLyrics.test.tsx`.

---

### 2026-10-15 — Pausing the radio actually stops it; the stray top player is gone

- Pause used to relabel a stream that kept encoding (the page read PAUSED with the clock still
  moving). It now stops Liquidsoap's Icecast output over harbor `/stop` (`/start` resumes
  mid-track); measured ~3.7% → ~0.3% CPU. `fallible=true` on `output.icecast` is required: 2.2
  raises "Source is infallible and cannot be stopped" otherwise.
- The backend's `is_playing` is the wish and the radio loop re-applies it each tick, so a pause
  survives a Liquidsoap restart. Top-up (LLM) is skipped while paused. RAD-02/03/04/07 amended.
- Radio page: the bare `<audio controls>` above the panel is gone (the panel button drives a hidden
  `<audio>`); tune-in is disabled while paused and a tuned-in listener is dropped when it pauses.
- **Who may:** pause stays editor+; **resume is open to any signed-in user** (human ruling,
  2026-10-15, ACCT-15 amended): starting is cheap, reversible, and only happens when someone wants
  to listen. A listener's tune-in on a paused radio calls `/api/radio/play` then connects, retrying
  for ~8 s while the Icecast mount comes back. The play BFF route now forwards the caller's real
  role instead of a constant `'editor'`.
- Tested against a throwaway Liquidsoap container on a `/stream-test` mount, not the live one.
  Tests: `tests/test_radio_pause.py`.

---

### 2026-10-15 — The radio page shows how many people are listening (RAD-14)

- The count is **Icecast's**, not ours: `radio_background_loop()` reads `/status-json.xsl` every 3
  ticks into `state["stream_listeners"]`; `/api/radio/state` returns it and the page shows "N people
  listening" beside the LIVE pill. The existing `active_listeners` (from `radio_listeners`) counts
  *open radio pages* — every poll registers — so it was the wrong number for "actively listening"
  and is left as observability only.
- Unknown is `None`, never 0 (PLAT-07); no source connected *is* 0. Parser handles Icecast's
  dict-vs-list `source` shape. Tests: `tests/test_radio_listeners.py`. Verified live: a client on
  `icecast:8000/stream` moved the API count 0 → 1 → 0.

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
