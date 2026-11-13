# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-11-10 (215 lines → ~185): the 2026-09-26 `docs/requirements/` entry moved to
> [memory/history_2025_2026.md](memory/history_2025_2026.md).
>
> Pruned 2026-11-08 again (209 lines → ~190): the 2026-10-23 phantom-lyrics entry moved to
> [memory/search_rag.md](memory/search_rag.md).
>
> Pruned 2026-11-08 (206 lines → ~195): the 2026-10-16 PROD-20 lyric-track entry moved to
> [memory/produce_console.md](memory/produce_console.md).
>
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

### 2026-11-13 — `deploy-changes.ps1`: deploy only what changed
The full deploy rebuilds and restarts everything. Restarting the backend also wipes its in-memory
render cache (`ChainCache`), so produce pages re-render every stem afterwards. The new script diffs
the last deployed commit (`.deploy-state.json`, also written by `deploy-production.ps1`) against the
working tree and maps paths to actions; mapping rules are in its `Classify`. The first run dates its
baseline from the running frontend image's build time. Not ported to `deploy-production.sh` yet.

### 2026-11-13 — Produce page: player in the version card, fixes inside console rows (PROD-24)
Owner found the page confusing during playback. The transport now lives in the version card (sticky
from `md` up). The card has a pencil for inline rename, a trash icon, a "Default version" checkbox,
and a **Start analysis | ▾** split button with Analyze & save and Separate stems on the menu. A
**Fixes** switch on the transport bypasses every fix for a whole-song A/B; it is listening-only and
feeds `useStemPlayback` the raw buffers, so it crossfades at the playhead. Clicking a console row
opens its fix cards beneath it. Each row's switch turns all its fixes off, and turns them back on to
the producer's own picks (`setRowFixesEnabled`). Removed: the separate fix panel and its "Full mix &
master" section (those fixes are the full-mix row's cards), **Hear it** with its whole `audition`
state machine (play + per-fix ON/OFF already A/Bs at the playhead), and `StemDetailPanel`, whose
"drag a region to limit fixes" never reached any render or save.

### 2026-11-10 — Analyze & save: one press from a version to a saved, cleaned version (PROD-23)
Owner asked for one button instead of Start analysis → wait → Save. It's the same server pass with
`then_save`, and the warm render it already started becomes a save. No pipeline was added. If
nothing is recommended, nothing is saved and the page says so. A render of different fixes is waited
out (`accept_jobs.wait`), because a one-press save that silently didn't happen is the worst outcome.
The saved version is an unpublished candidate, like any Save. See
[ARCHITECTURE.md](ARCHITECTURE.md) (search "Analyze & save").

### 2026-11-08 — Click repair works on real mixes; timing fixes stop adding clicks (song 917)
Cleaning 917 added pops: `_apply_time_map` butted independently stretched beat segments together, a
click per beat per stem, and each stem warped to its own grid (136-148 BPM on a 152 BPM song). The
detector needed a ~0.4 FS jump on a loud mix, so it found none of it. Now: joins crossfade; clicks use
a local per-frame predictor (`find_clicks`); `remove_artifacts` + `correct_beats` are measured on the
mix only, and `auto_clean` has a click step. `correct_beats` is manual-only (the band's drummer is
loose, so a tracked beat isn't truth). 917: 24 repairs/min, worst drum hit −0.43 dB. Full reasoning in
[ARCHITECTURE.md](ARCHITECTURE.md) (search "Clicks use").
Auto-enabling it when the mix/most stems agree was measured and declined: at mix confidence ≥0.5 only
3 of 18 stemmed songs pass, 1 with a stem majority agreeing (1824). `_detect_beats` confidence is onset
clarity, not agreement, so it selects drums (mean 0.58 vs guitar/bass 0.31). One shared map can't align
stems anyway; that needs per-stem warps, which move Demucs bleed and can't tell phrasing from error.

### 2026-11-08 — Follow-along lyrics: line starts snapped onto the voice

Lines lit up early because Whisper stretches a line's first word over the preceding silence: on 22
songs with stems, 20% of first words held 300+ ms of silence vs 2% of later words. `snap_line_starts()`
now corrects this during extraction from isolated vocals, and `scripts/snap_lyric_timings.py` corrected
those 22 songs (151 lines), confirmed by ear. Its `--separate` mode re-runs Demucs for the 1,084 timed
songs with no stems on disk, 7-16 s per song, resumable through `lyric_snap_done.json`.

---

### 2026-11-08 — Start analysis runs on the server, so you can leave and come back (PROD-22)

Leaving the produce page lost a pass: it was a loop of browser requests with findings in React
state. New `src/api/analysis_jobs.py` runs separate → measure → warm-render as a background job;
the last outcome per version lives in `song_version_analyses` (migration 26), retired once the
version is re-separated. The page polls on mount and reopens on the last-selected version. Two
things found on the way: every tool's `analyze()` ran CPU work on the event loop (now a worker
thread, as `apply` was), and a stem set left `running` by a restart would have been waited on
forever (`StemJobManager.is_running` guards it). Not stored: single-row re-analysis, and a
producer's toggles and added cards. Details in ARCHITECTURE.md.

---

### 2026-10-27 — SECURITY: live frontend compromised via React2Shell; Next 16.0.1 → 16.4.3

The prod frontend ran Next 16.0.1 / React 19.2.0 (CVE-2025-55182, unauthenticated RSC RCE). An
attacker ran code as `nextjs` in `bigflavor-frontend`: dropped an ELF at `/app/hxh` (sha256
`eee22e59…af12`, Defender: `Trojan:Linux/CoinMiner!rfn`), dumped env to `/tmp/.e7445c6ba/environ.txt` (leaked `SESSION_SECRET`,
`BACKEND_API_SECRET`, `GOOGLE_CLIENT_SECRET`), and injected a ClearFake/EtherHiding script (fake
captcha, payload fetched from BSC testnet contract `0xE75744C5…6b77`) in memory — nothing on disk.
Other containers showed no foreign files. Fix: Next 16.4.3, React 19.3.1, `npm audit fix` (prod deps
0 vulns). react-hooks 7.1.1's stricter rules flagged 18 sites; fixed 2026-10-28 without a pin:
derived state for the song page's version selection / bad id, "adjust state on a prop change" for
AudioProcessingTab's takes + region resets, layout effects for its latest-value refs, and a
reasoned `set-state-in-effect` disable on each fetch-on-mount effect (the rule can't see that the
loaders set state only after `await`). Postgres now publishes on `127.0.0.1:5432` only. Session + backend secrets rotated in `.env` and
`.env.production`; Google OAuth secret rotated in console (project `apikey-337918`); Postgres
password rotated as a precaution (`ALTER USER` + both env files; it was never in the frontend env).
Drive key (`secrets/`) is backend-only and showed no access; Anthropic key lives only in dev `.env`. Container removed,
image rebuilt `--no-cache --pull`. **Lesson:** run `npm audit --omit=dev` before every deploy — the
critical advisory sat open ~11 months.

### 2026-10-27 — Scan links each stem to its own channel, not one sharing its name

`_store_take` looked up a stem's `session_tracks` row by `(name, rec_pass)`, so the two "Drums in
stereo" mics (sessions 6 and 7) shared one `track_id`. `_PassScan.track_ids` now maps source file →
stored id and `render_take(track_ids=…)` sets `RenderedStem.track_id`; test in
`tests/test_session_render.py`. Existing data: 26 stems relinked in the live DB (52/67 instead of
53/68); 13 takes that kept only one of the pair are left pointing at the later mic — ambiguous.

### 2026-10-25 — …and joined back with its neighbour (SESS-23)

Each take card has "← Join with take N" / "Join with take N →" beside Split: only timeline
neighbours in one recording pass. `POST .../takes/{id}/join` puts both takes' audio back to back
(`session_render.join_rendered_takes`); the gap between detected takes was never kept, so it is
dropped (20 ms seam fade) and the confirm says how long it was. Transcripts are simply joined. **Found
while verifying:** the scan stored two same-named mics ("Drums in stereo" ×2) under one `track_id`
(fixed 2026-10-27, above), so channels are matched on (track id, name, order). Verified on real take audio: 7 channels in, 7 out.

### 2026-10-25 — A session take can be split in two at the playhead (SESS-22)

Freeish Birdish came out as one 25-minute take ("And for a king."), and nothing in review could
separate two songs sharing a take. Each opened take card now has **Split here**: click the waveform,
split. `POST /api/produce/sessions/takes/{id}/split` cuts the take's **own** mix and channels
(`session_render.split_rendered_take`; the raw recording is gone after a scan) into two **new**
takes, then deletes the original. New ids because `/preview` is cached `immutable` per id. First
half keeps the song, second gets a new group (or stays alone if the take was alone). A produced
take is released first. Words aren't timed in storage, so each half is re-transcribed in the
background: `transcript_pending` (**migration 25, applied to the local/prod DB 2026-10-25**) shows
"Listening for the words…" and `GET /sessions/{id}` resumes any read a restart cut short. Tests
are in `tests/test_session_produce.py`.

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
