# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-09-27 (740 lines → under the ~200 target): the six routine release entries
> (`v0.17.0` → `v0.19.0`) moved to [memory/releases.md](memory/releases.md); the seven produce /
> stem-console entries (2026-09-16 → 2026-09-21) to
> [memory/produce_console.md](memory/produce_console.md); the ESLint-config and event-loop entries to
> [memory/history_2025_2026.md](memory/history_2025_2026.md); and the Reaper session-import entry to a
> new [memory/sessions_import.md](memory/sessions_import.md). What stays is the radio work that is
> still load-bearing (issues #101 and #104) and the `docs/requirements/` contract.
>
> `memory/radio_streaming.md` was corrected in the same pass: its `mksafe()` invariant described the
> exact shape that caused #104, and it still described a backend-held radio clock that #101 deleted.
>
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
