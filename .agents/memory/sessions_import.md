# Recording Session Import — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) in the 2026-09-27 prune. Covers the Reaper rehearsal-session
upload/scan slice — how an uploaded session is unpacked, which songs are found inside it, and what
the scan deliberately does not do. Newest first.

---

*The entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-10-15 prune.*

### 2026-09-28 — A produced take can still move to another song (SESS-18 amended)
Owner asked to regroup takes after a song was already opened in the producer. Moving a produced take
(PATCH `takes/{id}` or "New song…") now calls `session_import.release_take`: one transaction
(`db.release_session_take_version`) deletes its version and the stem sets made from it and clears
`song_version_id`, then the copied audio/stem dirs are removed. If it was the default, the song is
left with **none** (SESS-15 — never auto-pick) and its radio override dropped. The take is staged, so
producing its new song brings it in. Review UI confirms before moving an "In catalog" take; Discard
stays hidden for those (delete the version on the produce page instead).

### 2026-09-28 — Session review only groups; producing a group makes a new catalog song (SESS-15/18/19/20)
The owner asked that the session page only group takes into songs, drop "Keep", and hand each song to
the produce page for analysis and the default choice. The keeper had never led anywhere: no import
step existed. Now each take has a song menu (move / on its own / new song), and "Produce this song →"
(`POST /sessions/groups/{id}/produce`, `src/api/session_import.py`) creates **one new song**, copies
each non-discarded take in as an unpublished `session`-label version with its channels as the
version's stem set, and navigates to `/produce/{songId}`. Details in `ARCHITECTURE.md`.

The owner's rulings, which are now requirements: session songs get ids from **1,000,000** up
(`session_song_id_seq`, clear of scraped ids); a session **never** matches an existing catalog song,
knowingly bending CAT-04; songs with **no default are hidden** from search, DJ and radio (SESS-20);
`keeper_take_id` is **dropped**.

- **Migration 24 is a manual step in production**, like 21 and 23 (the deploy scripts do not run
  migrations). It adds the sequence, `session_take_groups.song_id`, `session_takes.song_version_id`,
  and drops the keeper column. Search keeps working without it; the session page's produce button
  does not.
- **"No default → hidden" is keyed on the id range, not `audio_url`.** 688 of 1,415 catalog songs
  have a NULL `audio_url` and still play from `{id}_*.mp3`; the obvious rule would have hidden half
  the catalog. Checked against the live DB in a rolled-back transaction: the session song is hidden,
  then listed once a version is published, and 1,415 + 1 are listed.
- Verified end to end on session 4 ("Super Remodel", the owner's screenshot): song 1000000, versions
  "Take 1 (0:24)" / "Take 2 (3:59)", stem sets carry "4 Kev Vox" etc., a second press adds nothing.
  **Left in the local DB, no default chosen** — that choice is the owner's.
- Found, not fixed: session 4's takes have no stem for "5 Tom Instr (bass too high)" — the scan never
  rendered it, which is upstream of this change. Setting a default does not index audio, so a session
  song is not in audio-similarity or tempo search until a reindex.

### 2026-09-28 — Recording sessions import straight from Google Drive (SESS-16/17)
The owner asked to stop uploading multi-GB zips: the sessions already live in the shared `ReaperProjects`
Drive folder. `/produce/sessions` now has **Import from Drive** — the backend lists the dated project
folders and downloads one server-side (`src/production/drive_source.py`, migration `23`
`drive_folder_id`). Details in ARCHITECTURE.md "Sessions can come straight from Google Drive".

- **Setup is two things outside the repo:** a service-account key in `./secrets/` named by
  `GOOGLE_DRIVE_KEY` in `.env`, and the **Google Drive API enabled** on that key's Cloud project — a
  fresh key gets `403 … has not been used in project … or it is disabled` until it is. The folder is
  link-shared, so the service account needs no invite.
- The key file was first dropped at the repo root **un-ignored**; it now lives in gitignored
  `secrets/` (`*-drive.json` is ignored too). Adding `google-auth` means a backend **rebuild**, and
  the `./secrets` mount means a **recreate** (`docker-compose up -d backend`), not a restart.
- Download is `.RPP` first, then only the media it references; `.part` → rename only at Drive's
  exact size; `Range` resume on a drop. 17 offline tests in `tests/test_drive_source.py` fake the
  `requests` session.
- **The real Drive is not one-folder-per-night.** Nights are filed inside other nights' folders, one
  appears twice, some folders hold two projects, one project is empty, and `_Archive` holds 2008-era
  material. Discovery was rewritten around "a folder that directly holds a `.RPP`" after surveying all
  of it — the first design (walk the root's children) would have mixed nested nights' tracks into their
  parent and hidden 8 of 33 sessions.

### 2026-09-27 — Session takes are grouped by song, on a rule tuned against one nine-take session (issue #109)
Review showed one card per detected take with no song identity, so the band's several attempts at one
song read as strangers — and since a take's headline is six words of its own transcript (SESS-12), two
attempts could even render the *identical* card. New **SESS-13/14/15**; migration 21
(`session_take_groups` + `session_takes.group_id`); `src/production/session_grouping.py` decides it from
transcripts alone (no catalog match, no LLM, no acoustic measurement). Full detail in
[ARCHITECTURE.md](ARCHITECTURE.md); what the measurement taught:

- **Only one of the four thresholds is actually measured, and QA caught the first write-up claiming
  otherwise** (PR #115). Swept against the live session: `MIN_DISTINCTIVE_WORDS = 4` is the only knob
  whose value decides the outcome, and its margin is **one word** — at 3 the result becomes
  `[[2,3],[7,8]]` and the owner's headline case breaks, because take 8 has exactly 3 distinctive
  words. `START_ATTEMPT_GAP_SECONDS = 45` rests on a single data point (a 35.4s stop; flips at 36s,
  unchanged to 200s, **no upper bound measured**). `SAME_SONG_OVERLAP = 0.6` and `MIN_SHARED_WORDS = 3`
  are each **inert** on this session — sweeping the ratio 0.1-0.93 or the word count 1-10 changes
  nothing — and only jointly load-bearing: relax both and unrelated takes merge into `[[1,8,9]]`.
  The original claim "no unrelated pair reaches 0.30" was **false**: pair 4-7 scores containment
  **1.000** and is rejected by the shared-word count, which is the real reason that guard exists.
  **A wrong `why` on a magic number is worse than no comment** — it makes the next person preserve a
  margin that was never there. Sweep the constant before you write down what it does.
- Containment beats Jaccard (a restart is 8 words against 60) and the real pair of "Swinging Party"
  attempts scores **0.933** — that part held up. It is the *rejections* that were misattributed.
- **Complete-linkage was too strict and seed-linkage too loose.** Attempts that stopped at different
  points share only the opening, so requiring every pair to match grouped nothing; matching against the
  fullest take instead let the *transition* stretch — whose words contain both songs, so containment
  loves it — seed a group and swallow two songs. The rule that survived is **a take matching two takes
  that do not match each other is left alone**, which is order-independent and makes every group a
  clique. Its ceiling is asserted in the tests, not hidden: a full attempt bridging two disjoint
  partial ones has the same shape and also stands alone. **This rule is validated by unit tests only** —
  on the live session the partner sets are `{2: [3], 3: [2]}` and no take straddles, so the data that
  killed the two drafts is the *draft* behaviour, not a case the shipped rule ever handles in anger.
- **The straddler rule had to be enforced twice, and QA found the half that was missing.** Dropping a
  straddler from the words pass is not enough: the time rule below gated on "has words" for both of
  its two questions, so a straddler could still *seed* a group (`A / wordless / A+B / B` grouped the
  silence with the straddler). The fix needs **two** sets, not a swapped one — the take being attached
  *to* must be confidently placed, while the take being attached must be wordless. Swapping in the
  confident set alone, the obvious one-liner, fixes one direction and opens the mirror bug: a 50-word
  straddler then passes the "no words of its own" gate and gets attached as a start attempt. When one
  set answers two questions, splitting it beats renaming it.
- **The owner's own example could not be grouped by words at all.** Takes 8 and 9 are "So Tired", but
  take 8 is 69s of the band starting it with *nothing sung* — 3 distinctive words. Only time places it:
  the take immediately before a sung one, within 45s. **A transcript-based rule cannot see a take that
  has no transcript**, and that was the headline case, not an edge case. The 62s/89s gaps the first
  write-up cited as bounding that window **cannot bound it**: both are gaps between two *wordless*
  takes, and the rule only ever looks at a gap whose later take is sung. Check that a counter-example
  is reachable before quoting it as one.
- **What is stored is the human's corrections, not the guess.** Name, separated take and keeper persist;
  the name *guess* is derived at display time by reusing `takeName()`, so SESS-12's cap cannot drift and
  a stored name is only ever one a person typed. `keeper_take_id` has no default, so SESS-15 holds by
  construction. `POST /sessions/{id}/regroup` re-guesses from transcripts only — which is how the
  already-scanned session got grouped without re-uploading 2 GB, and why it is never automatic.
- Verified against that session end to end: 9 takes → groups `[2,3]` and `[8,9]`, takes 1/4/5/6/7 on
  their own, 9 takes still visible, no keeper, no names — exactly the owner's reading of the night.
  **But "verified" means one session with five comparable takes.** Treat the rule as tuned, not
  validated; the band's next upload is its first real test, and `MIN_DISTINCTIVE_WORDS` is the number
  to look at first when it guesses wrong.

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
