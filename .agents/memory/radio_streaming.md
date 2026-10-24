# Radio Streaming (Icecast + Liquidsoap)

*Reconstructed 2026-06-19 from commit `60da3f0` "Fixed radio" (2025-11-24) and the project CLAUDE.md.*
*Corrected 2026-09-27: the `mksafe()` invariant below described the exact shape that caused issue #104,
and the architecture section still described the in-process radio clock that issue #101 deleted. Both
are rewritten against the code as it now stands — see the #101 and #104 entries under **Later entries** below
for how each was measured.*

## Architecture

Live radio is decoupled from the FastAPI request/response cycle:

- **Backend** (`src/api/radio_service.py` + `src/api/routers/radio.py`) keeps radio state — current
  song, queue, play/pause, position — in **PostgreSQL** via `RadioStateStore` (issue #2), not in
  process, so it survives a restart. It writes the playlist file `streaming/playlist/radio.m3u` via
  `write_playlist_file()`.
- **Liquidsoap** (`streaming/radio.liq`) reads that playlist and streams audio to Icecast. It also
  runs a **harbor HTTP listener on container-internal port 8080** serving `GET /on-air` (what is
  actually playing: filename, title, source label, elapsed, remaining) and `POST /skip`.
- **Icecast** broadcasts at `/stream` (proxied by nginx).
- **Shared volume** `./streaming/playlist` is mounted into **both** the backend and liquidsoap
  containers, so the backend writes and Liquidsoap reads the same file.

**The stream is the source of truth for what is playing** (issue #101). The backend no longer runs a
clock of its own: `resolve_on_air_song()` asks `/on-air`, maps the filename back to a song id, and
takes `position` from the stream's `elapsed` each tick. The old simulated clock drifted away from the
audio and, when a song's `duration` was null, pinned Now Playing forever. Skipping goes to the stream
too — `POST /skip` moves the audio rather than only relabelling it.

Radio HTTP surface: `/api/radio/state`, `/api/radio/queue/add`, `/api/radio/queue/remove`,
`/api/radio/skip`, `/api/radio/play`, `/api/radio/pause`, plus `/stream`, `/stream.m3u`,
`/api/audio/stream/{song_id}`. Queue entries carry an `added_by` so a listener can remove their own
add (ACCT-05 / RAD-13); skip and play/pause are editor+.

## Two invariants (regressing either = silent dead air)

1. **Wrap the air chain in `mksafe()` once, around the *result* of the `fallback` — never around each
   child.** `mksafe` is itself an always-ready fallback to silence, so wrapping a child makes that
   child permanently ready and **everything after it unreachable**. That was the #104 defect: with
   `mksafe()` on each child, `fallback_music` was dead code from 2025-11 onwards, and a drained queue
   went to `safe_blank` — then, ~7 seconds later, Icecast logged `Disconnecting source due to socket
   timeout`, `/stream` began returning 404, and Liquidsoap never reconnected. Silence *and* a dead
   mount needing a human.

   ```liquidsoap
   # Correct: children stay fallible so they can yield; mksafe supplies the blank.
   radio = mksafe(fallback(track_sensitive=false, [radio_queue, fallback_music]))
   ```

   `track_sensitive=false` is deliberate: catalog music must yield promptly when a song is queued
   (RAD-08). No `blank()` child — `mksafe` *is* that blank.

2. **Rewrite playlist paths to Liquidsoap's mount points.** The backend writes audio paths as
   `/app/audio_library/song.mp3` but Liquidsoap mounts the library at `/audio_library`, so
   `write_playlist_file()` converts `/app/audio_library` → `/audio_library`. Audio files are matched
   by `{song_id}_*.mp3`.

## The fallback pool is Liquidsoap's own directory scan

`fallback_music` scans `/audio_library` directly, which is what keeps the last line of defence
independent of the backend, HTTP and Postgres. Two consequences:

- The scan is **recursive**, so it reaches `produced/…/stems/…` files whose names carry no song id. A
  `check_next` filter keeps only top-level `{song_id}_*.mp3`.
- A file whose id has **no `songs` row** still plays (74 such files as of 2026-09-27 — issue #107).
  `_song_from_stream()` names those from the stream's own ID3 title, falling back to the filename, so
  the page never claims silence over audible audio (RAD-05). Do **not** "fix" this by filtering the
  pool against the `songs` table: that would put Postgres back in the path of the fallback and cost
  those songs their only route to air.

## Operational gotcha — Liquidsoap config rebuilds

Docker BuildKit aggressively caches the `COPY` layer for `streaming/radio.liq`. A plain
`docker restart` or even `docker-compose build` (without `--no-cache`) will **not** pick up changes —
it will silently keep running the old config, which makes any verification worthless. Force it:
```bash
powershell -Command "(Get-Item 'streaming/radio.liq').LastWriteTime = Get-Date"
docker stop bigflavor-liquidsoap && docker rm bigflavor-liquidsoap
docker-compose build --no-cache liquidsoap
docker-compose up -d liquidsoap
```
Confirm what is actually running before trusting a measurement:
```bash
docker exec bigflavor-liquidsoap md5sum /etc/liquidsoap/radio.liq   # compare to the committed file
```

Debug with `docker logs bigflavor-liquidsoap --tail 100`, or ask the stream directly:
`docker exec bigflavor-backend curl -s http://liquidsoap:8080/on-air`. If it is streaming
`safe_blank` instead of the playlist, suspect the air-chain shape (invariant 1) or a path-rewrite
mismatch (invariant 2).

**`reload_mode="watch"` does not fire on the Docker Desktop/Windows bind mount** — it needs inotify,
so on Windows the queue playlist only reloads at container start. Force one over telnet when testing:
`docker exec bigflavor-liquidsoap bash -c 'echo "radio.m3u.reload" | telnet localhost 1234'`.

---

## Later entries

*The entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-10-15 prune.*

### 2026-09-26 — An empty radio queue served silence, then a dead Icecast mount (issue #104)
`mksafe()` was wrapped around **each child** of the air `fallback`, so the queue source was always
ready and `fallback_music` could never be selected — dead code since 2025-11. Measured the real
outcome on the live stack before writing anything, and it was worse than the issue said: with an
empty `.m3u`, `[playlist parser:3] No format found` → `[radio.m3u] Playlist stopped.` →
`[mksafe:3] Switch to safe_blank.`, and **7 seconds later Icecast logged
`Disconnecting source due to socket timeout`** and `/stream` returned **404 and stayed 404** —
Liquidsoap never reconnected. So the failure was not "quiet radio", it was a dead mount that needed a
human to restart a container. RAD-02, RAD-03 and RAD-10 were all unmet.

- **`mksafe` stays; where it goes is the fix.**
  `radio = mksafe(fallback(track_sensitive=false, [radio_queue, fallback_music]))`. The children stay
  fallible so they *can* yield; the always-ready net sits once at the top, so the output still cannot
  fail. Generalizable: **an always-ready source is only ever correct as the last thing in a chain** —
  put it anywhere earlier and everything after it is unreachable by construction. `blank()` left the
  list for the same reason (mksafe *is* that blank).
- **`AGENTS.md` was part of the bug.** It had prescribed `mksafe(radio_queue)` + `mksafe(fallback_music)`
  + `fallback([…, blank()])` verbatim for a year, so the defect was the documented invariant. Corrected
  in `AGENTS.md`, `.agents/CODING.md`, `.agents/ARCHITECTURE.md` and `.agents/TESTING.md` in the same
  commit — otherwise the next reader "fixes" it back.
- **`track_sensitive=false`** or catalog music would hold the air until its track ended (minutes)
  while a listener's queued song waited (RAD-08). Measured: 2s from playlist reload to the queued song
  on air; 1s back to catalog music when the queue drained. No mid-track flapping — `mksafe` is itself a
  `track_sensitive=false` fallback and its log showed blank switches only at startup, never between
  tracks, which is what made this safe to choose.
- **The catalog source had to be filtered before it could ever play.** `playlist("/audio_library")`
  scans **recursively**, and the directory holds `produced/` (Demucs stems, `.opus` previews) and
  `sessions/` as well as the songs — 2,255 files against 1,415. Caught it queueing
  `produced/…/previews/guitar.opus`. Broadcasting a lone guitar stem is bad enough; its filename has no
  song id, so `song_id_from_filename()` returns `None` and the page shows *nothing playing* over
  audible audio (RAD-05). `check_next` keeps only top-level `{song_id}_*.mp3`. **Making a source
  reachable means auditing what it will actually serve** — nobody had, because nothing ever played.
- **Verified by measuring the broadcast, not by reading the config**, which is the only honest way with
  this bug: 320s continuous empty-queue listen at `mean_volume -15.2 dB` with exactly one sub-second
  dip below -50 dB, at a song boundary with no source switch in the log (the tracks' own tail/head).
  Before: 404. `switch → catalog_fallback` and `Prepared` from `audio_library` appear in the log for
  the first time ever. `/api/radio/state` named the fallback song and labelled it `fallback` with
  position within ~1s of the stream — PR #103's display half exercised for the first time, unchanged.
- **Liquidsoap escaping, learned the hard way:** `"\."` inside a `.liq` string is a **parse error**,
  not an escaped dot. Used `[.]` instead. And the bash-tool→heredoc path silently halves backslashes,
  so build such patterns with `chr(92)` or avoid them. `liquidsoap --check` catches both (proved it by
  feeding it a deliberately broken chain) — always `--check` before the rebuild.
- **Separate defect found and left alone:** `reload_mode="watch"` never fires on a Docker
  Desktop/Windows bind mount — 5 queue-playlist reloads in a day, all at container start, against
  hundreds of backend writes. Queue changes reach the air on Linux via inotify but not on this dev
  stack, so local queue verification needs a forced `radio.m3u.reload` over telnet (port 1234, reachable
  from the nginx container). Nothing to do with the fallback chain; reported, not fixed.

- **QA caught the half of RAD-05 the filter cannot cover, and it is the generalizable lesson here:**
  a filename's *shape* is not proof of a catalog row. The stream's fallback pool is a directory scan,
  the catalog is a table, and they disagree — **74 of the 1,415** top-level `{song_id}_*.mp3` files have
  no `songs` row (no row lacks a file), so about every 19th fallback track resolved to an id
  `_load_catalog_song()` returned `None` for, and the page said *nothing playing* over audible music
  exactly as the stems would have. Fixed where naming lives, not by shrinking the pool:
  `resolve_on_air_song()` falls back to `_song_from_stream()` (ID3 `title`, else the filename with the
  id prefix stripped) and the length comes from `stream_duration`, as it already did for catalog songs
  with no duration. **Shrinking the pool to ids in the database was the other option and is worse** —
  it would drop 74 playable songs and make the stream's last line of defence depend on Postgres and the
  backend being up, i.e. re-risk the very requirement (RAD-02) this issue restored. The 74 orphan files
  are a catalog-data defect of their own and are reported separately, not designed around. Reproduced
  live both ways by pointing the fallback source's `audio_library.uri` at an orphan-only playlist over
  telnet — 1/1415 odds are not a test plan, and the first PR's RAD-05 check passed only by landing on a
  song that happened to resolve.

`tests/test_radio_air_chain.py` (7 cases) pins the chain's shape — confirmed red against the old
config before keeping it — because what regressed was a shape, and the cross-checked filter regex
doubles as a real test of which paths the fallback will accept. The two `/api/audio/stream` Range
tests in `test_api_routers.py` still fail on `main`; untouched, no Python changed here.

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

*The entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-10-24 prune.*

### 2026-10-15 — The radio page shows the on-air song's lyrics

- A **Lyrics** toggle in Now Playing opens `components/RadioLyrics.tsx`, which reads the existing
  listener-scoped `/api/songs/{id}/lyrics/timed` and reuses `LyricsFollower` when timings are
  followable; otherwise it shows the plain text, or "No lyrics for this song." No backend change.
- The radio has no local clock, only the 3 s polled `position`: `RadioLyrics` re-anchors on each
  poll and runs the clock forward with rAF between polls (held while `is_playing` is false). Lines
  are not seekable — the stream is shared (RAD-01). The polled position is the server's, so the
  highlight can run a few seconds ahead of what a listener hears through Icecast's buffer.
- Tests: `frontend/__tests__/RadioLyrics.test.tsx`.

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

### 2026-10-15 — The radio page shows how many people are listening (RAD-14)

- The count is **Icecast's**, not ours: `radio_background_loop()` reads `/status-json.xsl` every 3
  ticks into `state["stream_listeners"]`; `/api/radio/state` returns it and the page shows "N people
  listening" beside the LIVE pill. The existing `active_listeners` (from `radio_listeners`) counts
  *open radio pages* — every poll registers — so it was the wrong number for "actively listening"
  and is left as observability only.
- Unknown is `None`, never 0 (PLAT-07); no source connected *is* 0. Parser handles Icecast's
  dict-vs-list `source` shape. Tests: `tests/test_radio_listeners.py`. Verified live: a client on
  `icecast:8000/stream` moved the API count 0 → 1 → 0.
