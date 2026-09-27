# Recording Session Import — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) in the 2026-09-27 prune. Covers the Reaper rehearsal-session
upload/scan slice — how an uploaded session is unpacked, which songs are found inside it, and what
the scan deliberately does not do. Newest first.

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

---
