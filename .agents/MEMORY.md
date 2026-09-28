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

### 2026-09-28 — Three broken search functions retired rather than repaired (issue #114)
`search_by_tempo_and_audio`, `search_songs_hybrid` and `search_similar_songs_by_text` had raised on
*every* call since migration `04` (`song_id VARCHAR(50)` against an integer; the two text-side ones also
referenced `te.text_embedding`, gone since text embeddings moved to all-MiniLM-L6-v2). The owner's call
was **delete, don't fix** — "if it turns out we need them in the future, we can always add them back
in". Migration `22` drops all three by signature; their three uncalled `SongRAGSystem` methods
(`search_by_text`, `search_hybrid`, `search_by_tempo_and_audio`) are gone, as are
`database/update_search_functions.sql`, `database/apply_search_update.py` and
`tests/update_search_functions.ps1`.

- **Absence of a caller is the whole justification, so it is the thing to verify — not the test run.**
  Every SRCH-02 mode is served by a *different*, working path (`search_by_text_description`,
  `search_lyrics_by_keyword`, `search_by_tempo_range`, `search_text_with_tempo`,
  `search_similar_songs_by_audio`), which is why deleting these breaks nothing. Confirmed by measuring
  all five endpoints plus `/api/songs/{id}/related` live after the drop, not by reading the code.
- **The trap is name collisions, and there were three layers of them.** `src/api/routers/search.py`
  has *route handlers* named `search_by_text` and `search_hybrid`; `src/agent/big_flavor_agent.py`,
  `src/api/research_jobs.py` and `src/rag/deep_search.py` carry an agent *tool* called `search_hybrid`
  that dispatches to `_perform_hybrid_search`; and `tests/rag_mcp_server.py` has its own `search_hybrid`
  composing working methods. All four are live and all four stay. **Delete by call graph, never by name.**
- **A hand-run SQL file that re-creates functions can silently undo a migration, and this one would
  have.** `update_search_functions.sql` still carried the pre-migration-`20` `song_id VARCHAR(50)`
  declaration for `search_similar_songs_by_audio`, so re-applying it would have re-broken the mode PR
  #113 had just fixed. Retiring the file *is* the fix; migrations are the only path.
- **A dead function is worse than dead code**: it looks available, and the first caller discovers it
  is not. Nothing reported any of this for ten months (the same blind spot as **CAT-12**). A smoke
  check that every remaining search function answers was deliberately left to its own issue.
- `tests/test_rag_hybrid_dimensions.py` went with `search_hybrid` — all three of its tests covered only
  that method's placeholder-vector behavior, so no coverage of anything that still exists was lost
  (746 → 743 passing, same 13 pre-existing failures).
- **Migrations `21` and `22` are both unapplied in production.** `22` is applied on the dev stack.

---

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

---

### 2026-09-27 — Audio similarity had never used CLAP, and the "one-word fix" was three (issue #111)
`clap_embedding` was NULL for all 1,415 rows back to 2025-11-09, so every `combined_embedding` was the
librosa fallback and "find me more like this" ranked on recording texture. Reported in #107, fixed
here. **Measured on the live stack before writing anything, and the issue's premise was too small** —
full detail in [ARCHITECTURE.md](ARCHITECTURE.md); the three findings are:

- `clap_processor(audios=)` → `audio=` is only the first break. transformers 5's
  `get_audio_features()` returns a `BaseModelOutputWithPooling`, not a tensor, so the kwarg fix alone
  died on `'BaseModelOutputWithPooling' object has no attribute 'cpu'`. The embedding is its
  `pooler_output`. **Distrust a one-word fix to dependency drift** — a rename rarely moves one thing.
- **A working CLAP vector did not fit the column.** The combined representation is 37 librosa dims +
  512 CLAP = **549**; `init/03` said so and migration `04` re-created the table at `vector(512)`,
  unnoticed for ten months because CLAP never produced a vector to store. Shipping only the kwarg fix
  would have failed *every* insert. Migration `19` restores 549, guarded on `atttypmod` so a re-run
  cannot wipe the rebuilt vectors.
- **The report was the third bug and the reason this lasted.** `index_audio_file` stored a CLAP-less
  row and returned `True`, so a batch said `{'total': 74, 'success': 74, 'failed_files': []}` with zero
  CLAP embeddings in it — #107's lesson one level up: there a blanket `except` turned an error into
  missing data, here the *caller* turned missing data into a success. New **CAT-12** forbids it, and
  the guard sits at the one seam so the scrapers, batch indexer and produce approval all inherit it.

**Mixed embedding spaces are now prevented structurally, not by discipline** (new **CAT-11**): a
fallback vector is 512 wide and a CLAP one 549, so they cannot share the column, and a not-yet-rebuilt
row is NULL, which the search functions' `>=` threshold drops. The rebuild therefore compared a
growing *subset*, every comparison CLAP-vs-CLAP — never an error, never two spaces. The rejected
alternative (staging column + atomic cutover) keeps coverage whole but leaves `index_audio_file` not
knowing which column is live, breaking the incremental path (**CAT-08**) for the same window.

`scripts/reindex_audio_embeddings.py` **updates rows and never inserts them**: `audio_embeddings` is
unique on `audio_path` and 1,341 rows still held a host-written Windows relative path that cannot open
in the container, so upserting on a freshly resolved path would have created a second row per song and
returned each twice (**CAT-04**/**CAT-07**). Resumable by construction (a row with both halves is
done), and it refuses to run where CLAP is unavailable.

**How bad the fallback was:** 475 of its 512 dims are zeros, so the whole catalog sat in a
37-dimensional cone and every pair scored **0.994-1.000** similar. Ranking was noise in the fourth
decimal.

---

### 2026-09-27 — 74 playable songs were not in the catalog, and indexing had silently stopped (issue #107)
`audio_library/` held 1,415 top-level `{song_id}_*.mp3` files against 1,341 `songs` rows. The 74
without a row were playable but undiscoverable: search, the DJ, lyrics and embeddings all start from
the catalog, so the radio's own directory scan was the only way they could reach a listener (**CAT-01**
— a song that cannot be surfaced by any search mode is a defect). Found while fixing #104, which only
made them audible.

**Cause, from the cached scrapes rather than a guess.** `scraper/scraped_songs_20251106_173012.json`
still describes 60 of the 74; the 2025-11-10 scrape the catalog was loaded from describes **none** of
them. They were dropped between the two scrapes and their files stayed behind. So the back-fill
(`scripts/backfill_orphan_songs.py`) prefers that older scrape — keyed by slug, numeric id inside
`audio_url` — then the file's own ID3 title via ffprobe (14 songs), then the filename (0 needed).

**The real find was that indexing was dead.** The first back-fill run filled *nothing*: 74 failures,
all "no usable features". `librosa.beat.beat_track` returns tempo as a 1-element array and numpy 2.5
refuses `float()` on one; a blanket `except` around the whole feature block turned that into an empty
dict. **Every song indexed since the librosa 1.0 / numpy 2.5 upgrade had lost its tempo, key and
duration** — invisible because the 1,341 rows indexed before it still had theirs. `as_scalar()` fixes
it; the lesson is the blanket `except`, which made a type error indistinguishable from "this song has
no tempo".

**Delivered:** 74 rows inserted; duration + tempo now 1,415/1,415; metadata embeddings 1,415/1,415, so
the songs are findable (spot-checked: 2343, 2538 rank first for their titles, 890 first for its own);
audio embeddings 1,415/1,415.

**Left undone, deliberately:** those 74 still have no lyrics (Whisper hours) and therefore no genre,
which `derive_genre` infers *from* lyrics — so they rank on title alone; 1063 "So Tired" sits 19th
among ~18 same-titled songs. Also found: **`clap_embedding` is NULL for all 1,415 rows going back to
2025-11-09** — CLAP has never worked here (`clap_processor(audios=…)` is the kwarg transformers
renamed), so every `combined_embedding` is the librosa fallback. Left alone on purpose: fixing the
kwarg now would give 74 songs CLAP vectors while 1,341 keep fallback ones, which is a worse state than
uniformly-degraded (**CAT-05**). It needs its own issue and a full re-index.

**Also:** `scraper/` is now mounted read-only into the backend container beside `scripts/`, because the
back-fill reuses the scraper's own `insert_song_with_details` and reads those cached scrapes.

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
