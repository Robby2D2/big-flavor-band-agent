# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

> Pruned 2026-09-14: the `/produce` per-tool API and stem-console entries (2026-07-31 →
> 2026-08-02) moved to [memory/produce_console.md](memory/produce_console.md); the 2026-07-12
> pipeline-concurrency entry moved to [memory/history_2025_2026.md](memory/history_2025_2026.md).
>
> Pruned 2026-08-01: routine release-manager version-bump entries moved to
> [memory/releases.md](memory/releases.md); the 2025-11 project-genesis timeline and two older one-off
> incident writeups moved to [memory/history_2025_2026.md](memory/history_2025_2026.md). This file now
> holds only the recent, still-load-bearing entries.

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

### 2026-09-15 — First prod deploy in a while: the image build had been broken for weeks
`docker-compose --env-file .env.production build` failed immediately: `npm ci` refuses a
`package-lock.json` out of sync with `package.json` (missing `@emnapi/*`). Broken since `0fe6e4e`
and invisible locally, because `npm install` is lenient and only `npm ci` — what the Dockerfile
runs — is strict. **Nobody had deployed since.**

Regenerating the lock exposed a second latent break: the vitest suite imported `screen` from
`@testing-library/react`, which only re-exports it from `@testing-library/dom` — a **peer**
dependency that was never declared and that `--legacy-peer-deps` does not install. It had merely
been sitting in a stale `node_modules`. A clean install failed all nine test files. Now declared
explicitly, so a from-scratch install (CI, Docker) reproduces a working suite.

**Prod is this machine.** `deploy-production.sh` runs the same `docker-compose.yml` with a
different env file — same container names, same Postgres volume. So "deploying" does not migrate
anything: the prod database *is* the dev database, which is why migration 13 and the metadata
embeddings were already live. Checked `POSTGRES_PASSWORD` matches between `.env` and
`.env.production` before recreating containers — a mismatch would have locked the backend out of
its own data volume, since Postgres only applies that variable on first init.

Deploy-time differences that actually bite:
- `SESSION_SECRET` differs per environment by design, so **every deploy that flips env logs
  everyone out**.
- `OLLAMA_MODEL` is `mistral-nemo` in dev, `qwen2.5:14b` in prod. Explanations work on both;
  qwen's first call after a restart takes ~13s while the 9 GB model loads, then it is fast.
- The frontend runs `NODE_ENV=development` even in prod: `docker-compose.yml` hardcodes it rather
  than reading `${NODE_ENV}`, so the value in `.env.production` is dead. Pre-existing.
- `deploy-production.sh` prints "3. Set up the database with migrations" but runs no migrations.

Post-deploy verification that matters: liquidsoap logs `Switch to safe_blank` **at startup** and
then recovers once sources are ready — check the *tail*, not the boot lines, or it reads as the
blank-source regression. It was queuing real `/audio_library/…` files a minute later, path rewrite
intact.

---

### 2026-09-15 — Search accuracy was never the LLM's fault
Complaint: results are poor and search is slow. The assumption was the local model. Measured first:
`/api/search/text` (no LLM) and `/api/search/natural` (agent) returned **byte-identical ordering and
scores** — 0.483, 0.449, 0.430, 0.426, 0.413 — in 0.04s and 11.6s respectively. `search_songs`
calls `search_by_text_description` directly and then only asks the LLM to write a sentence per
result. The model contributed nothing to ranking and 100% of the latency.

Three real defects, all in the SQL:
1. **Only lyrics were embedded.** `text_embeddings` held 1,338 rows, all `content_type='lyrics'`.
   Genre, mood and energy were invisible to semantic search.
2. **The keyword branch used the whole query as one `ILIKE '%…%'`**, so any multi-word query matched
   nothing lexically.
3. **Keyword hits scored a flat 0.5**, replacing the semantic score. Searching `punk` returned five
   songs at *exactly* 0.500, tie-broken alphabetically — no relevance ordering at all.

Fixes:
- **`src/rag/search_text.py`** (pure, unit-tested): `build_metadata_text` renders title/genre/mood/
  energy/tempo/key as a labelled sentence to embed; `tokenize_query` splits the query, drops
  request-describing stop words ("find me some songs"), keeps apostrophes (so "don't" never becomes
  "don" and substring-matches London), and splits on `_` because underscore is a single-character
  **ILIKE wildcard**.
- **`scripts/backfill_metadata_embeddings.py`** — one `metadata` row per song, batched on GPU.
  1,341 songs in seconds. Idempotent; re-run after any metadata change.
- **Scoring is now `semantic + keyword_bonus`**, capped at 1.0. First attempt made keyword a rival
  score (`GREATEST` + a fraction of `LEAST`) and it was *worse*: a lone title substring outranked
  genuine matches, Country Roads fell to 5th for "upbeat country song about home", and everything
  compressed into 0.744-0.743. As a bonus (0.10 per controlled-vocabulary hit, 0.05 per title
  substring, capped 0.30) semantic leads and Country Roads returns to 1st at 0.638 with clear air.
- Every candidate is scored semantically **even when it surfaced only via keywords** — otherwise
  same-genre songs all tie on the bonus and fall back to alphabetical.

Results now: `punk` → all punk, 0.664→0.651 differentiated. `high energy rock` → all rock/high,
0.808 top. Search 26-60ms.

**Explanations moved to `/api/search/explain`** (`src/rag/explain.py`), one song, on click. The old
per-result commentary was ungrounded — it captioned a catalogue cover of "Country Roads" with an
invented claim that Bob Dylan wrote it under a pseudonym, and the leading `": "` showed the JSON
parse had failed and fallen back to slicing fragments. The new prompt supplies only that song's own
facts and forbids inventing authorship or history. Grounded output, 0.3-0.7s warm, and it blocks
nothing. Full BFF round-trip: search 0.16s (was 2-12s), explain 0.72s on click.

Verified no regressions by diffing the full pytest failure set against a `git stash` baseline:
13 before, 13 after, identical — all stale demo scripts calling methods that no longer exist
(`SongRAGSystem.initialize`, `DatabaseManager.disconnect`).

---

### 2026-09-15 — "Lyrics not found" was a BFF route that never existed
The view-lyrics modal on the search screen had shown "Lyrics not found" for every song since
`60da3f0` (2025-11-24). Not a data problem and not a regression from the auth work that day: the
backend held the lyrics all along (`GET /api/songs/1299/lyrics` → 200 with the full text), but
`SongList.tsx` fetched `/api/songs/{id}/lyrics` and **no route handler was ever created for it**.
`git log` on that path returns nothing.

Only `/api/agent/*` is proxied by a `next.config.js` rewrite, so every other backend path the
browser calls needs a handler under `app/api/`. Without one Next answers a plain 404, the
component's `else` branch runs, and the UI renders a confident, wrong sentence. The sibling
`/lyrics/timed` route existed, which is what made the gap easy to miss.

- **Fix:** `frontend/app/api/songs/[songId]/lyrics/route.ts`, mirroring its `timed` sibling —
  `requireAuth(LISTENER)`, proxy, and map Unauthorized/Forbidden to 401/403 so the modal can tell
  "please log in" apart from "this song has no lyrics".
- **`frontend/__tests__/bffRoutes.test.ts` guards the whole class of bug:** it walks client-side
  source for literal `/api/` fetches, normalises `${...}` to a placeholder, and resolves each path
  against `app/api/` on disk (honouring `[param]` directories and the rewrite prefixes). Verified it
  actually fails without the fix — it names the offender as
  `components\SongList.tsx -> /api/songs/${...}/lyrics`. A green test that was never seen red is
  not a regression guard.
- `lyricsRoute.test.ts` covers the handler's behaviour: passes lyrics through, asks for `listener`
  (not `editor`), forwards a backend 404, and maps auth failures.

**Doc correction:** yesterday's ARCHITECTURE entry claimed "every backend route requires the service
secret". False — `search.py` (9 routes) and `agent.py` (3) have no `require_role` at all, and
`radio.py` guards 5 of 9. Only admin/produce/tools are fully covered. Corrected in place; closing
that gap is still open work.

**Dev-server gotcha:** a *new* route file under the read-only `./frontend/app` bind mount is not
picked up by `next dev`'s watcher — the file is visible inside the container but the route still
404s until `docker restart bigflavor-frontend`. Editing an existing file hot-reloads fine.

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

---

### 2026-09-15 — The session cookie was a claim, not a credential; now it is signed
Two holes closed, both found while building editor invites. Neither needed a clever exploit.

**1. The `appSession` cookie was unsigned JSON.** `{"sub":…,"email":…}`, URL-encoded, and every
reader just `JSON.parse`d it. `HttpOnly` stops page scripts from *reading* it but does nothing about
*writing* one — `curl -H "Cookie: appSession=…"` with an admin's Google `sub` was a full admin
session. Verified against the running stack before the fix and after: the same forged cookie now
gets 401.

- **`frontend/lib/session.ts`** is the whole fix: `base64url(payload).HMAC-SHA256(payload)` keyed on
  a new `SESSION_SECRET`, constant-time compare, and **`exp` inside the signed payload** so a
  captured cookie cannot be replayed with a fresh `Max-Age`. Fails closed everywhere — no secret,
  bad signature, or past expiry all read as "not signed in".
- A **separate secret from `BACKEND_API_SECRET`** so the two blast radii stay separate. Distinct
  values per environment; both `.env` and `.env.production` got one, and the deploy scripts now
  refuse to start without it. **Changing it logs everyone out** — as did shipping this.
- `Secure` is set when the request arrived over HTTPS, so prod gets it without breaking
  `http://localhost`.

**2. `POST /api/users` and `GET /api/users/{id}/role` had no `require_role`.** Unlike every
`/api/admin/*` route, anything on the Docker network could create users or enumerate anyone's role
by id. Both now take `require_role("listener")` — BFF-only, not admin-only, since the BFF calls them
for whoever just signed in. The three BFF call sites now send `backendAuthHeaders('listener')`.

**3. Found while fixing the above: `requireAuth` failed *open*.** The role check ran only inside
`if (response.ok)`, so a backend 404 or 500 skipped it entirely and returned the user — passing an
admin check. It now fails closed: an unreadable or unknown role is a refusal.

**Known wart, deliberately left:** an unauthenticated call to a BFF route answers **500**, not 401 —
the ~45 route handlers all map `error.message.includes('Forbidden') ? 403 : 500`. Access is correctly
denied either way; fixing the status properly means touching every one of those files.

Verified live: forged old-format cookie → 401; payload swapped to the admin's `sub` with a valid
signature kept → 401; real editor session → admin route → 403; real admin session → 200 with data;
user routes → 401 with no/wrong service secret and 200 for the BFF. 81 backend tests pass (10 new),
58 vitest (14 new, including "the old unsigned format is rejected"), `tsc --noEmit` and
`npm run build` clean. The four audio-streaming failures in `test_api_routers.py` /
`test_blocking_io.py` fail on a clean tree too — pre-existing, unrelated.

---

### 2026-09-14 — Editor invites: a copyable link, because there is no mail stack here
Adding an editor used to mean `UPDATE users SET role='editor'` by hand — the only path, since every
Google sign-in lands as `listener` and nothing in the app could grant more. Now an admin creates an
invite on `/admin` and copies a link to send however they like.

**Why a link and not an email.** There is no SMTP, mail library, or mail secret anywhere in this
stack. Sending mail would mean a new dependency, four new production secrets, and SPF/DKIM records
or every invite lands in spam — for a handful of invites a year. The admin sending the link
themselves needs none of that.

- **`src/invites.py`** holds the rules as pure functions (no DB, no I/O) so the things that actually
  gate access are unit-testable: 7-day expiry, single use, revocable, and **bound to the invited
  email** — you must sign in with Google as that exact address, so a forwarded link is worthless.
  Only `editor` is invitable; `admin` stays a deliberate promotion on the role dropdown.
- **Only the SHA-256 hash of the token is stored** (`user_invites`, migration `13`). The raw token
  is returned exactly once, at creation, so a database dump cannot be replayed into editor access —
  and the admin UI says the link will not be shown again.
- **Single use is the `WHERE` clause**, not a read-then-write: `DatabaseManager.redeem_invite`
  guards on `redeemed_at IS NULL AND revoked_at IS NULL AND expires_at > CURRENT_TIMESTAMP` in the
  `UPDATE` itself, so two concurrent redemptions cannot both succeed.
- **Crossing the OAuth round-trip:** `/invite/<token>` → `/api/auth/login?invite=…` stashes the
  token in a 10-minute HttpOnly/Lax cookie → the callback upserts the user, redeems, and redirects
  to `/invite/accepted`. A cookie rather than the OAuth `state` param, because `state` is unused
  here today and repurposing it would have meant rewriting the auth route's CSRF story too.
- The callback now tracks whether the user upsert **succeeded** — a role can only be granted to a
  user row that exists, and that save was previously fire-and-forget.
- `scripts/run_migration.py` was hardcoded to migration `05`; it now takes the filename as an
  argument and lists what is available when the name is wrong.

Verified end-to-end against the live stack (no curl in the backend image — drive it with `python -m`
+ `httpx` inside the container): create → preview → wrong-email reject → redeem → re-redeem reject,
plus 403 for a non-admin creator and 400 for an `admin`-role invite. 46 backend tests, 44 vitest,
`tsc --noEmit` and `npm run build` all green; test rows cleaned up afterwards.

**Still open (pre-existing, not introduced here):** the `appSession` cookie is unsigned JSON, so
anyone who can set a cookie and knows an admin's Google `sub` gets admin; and `POST /api/users` /
`GET /api/users/{id}/role` carry no `require_role`, unlike every `/api/admin/*` route.

---

### 2026-09-14 — "Unexpected token '<'" in the produce tab is a 60 s proxy timeout, not a bug in the app
Playing pending fixes and "Accept all & save version" both failed with
`Unexpected token '<', "<html> <h"... is not valid JSON`. Traced end to end: the app itself never
sent that. `docker logs bigflavor-nginx` shows the failing calls (six `stems/N/preview-chain` at
21:13:36, `accept-fixes` at 21:17:00) logged as **499 — client closed request**, while
`docker logs bigflavor-frontend` shows the same calls *completing* in 60–61 s. So the stack is fine;
something **in front of our nginx** (the edge proxy for `bigflavor.useunix.com`, not in this repo —
our own `/api/produce` block is already 300 s) hangs up at 60 s and hands the browser its own HTML
error page. `res.json()` then died on `<html>`.

Two changes, both frontend:
- **`lib/apiJson.ts` / `readJson(res)`** — every `app/api/` route answers in JSON, successes and
  errors alike, so a body that doesn't parse came from a proxy. It now reports
  "The server was still rendering when the proxy gave up (504)…" instead of a parser message. Wired
  into every fetch in `useProcessingQueue`; the two `analyze` calls now check `res.ok` *before*
  reading the body, so a proxy error page no longer throws out of a pass that was meant to tolerate
  one tool failing.
- **`lib/concurrency.ts` / `mapWithConcurrency`** — `handleTogglePlay` fired all six stem renders at
  once. The DSP is CPU-bound server-side, so that doesn't finish the batch sooner, it just stretches
  every request to the length of the whole batch (six parallel `stems/N/preview` GETs took 32 s each;
  serial they're ~5 s) — straight past the 60 s cutoff. Capped at `RENDER_CONCURRENCY = 2`.
  `runAnalyzeJobs` now uses the same pool.

**Still open for a human:** a whole-song accept-fixes pass (18 fixes over six stems + master) takes
longer than 60 s no matter how it's scheduled. It needs either a higher `proxy_read_timeout` on the
edge proxy or the job+poll treatment the batch endpoints already use.

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

