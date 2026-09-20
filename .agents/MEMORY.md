# Memory — Big Flavor Band Agent

Rolling, **dated** record of the project's most relevant state and the key changes behind it. Newest
entries at the top. When this file approaches ~200 lines, move older entries into topic files under
`.agents/memory/` and link them from [LONGTERM_MEMORY.md](LONGTERM_MEMORY.md).

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

### 2026-09-20 — Released v0.17.0 (minor bump — 58 commits, first release since v0.16.2)
Tagged `main` at `2412341` as **v0.17.0**. Minor rather than patch: the range carries real new
capability, not just fixes — timed lyrics with follow-along highlighting, editor invite links (and
the auth holes closed building them), the full mix + real transport in the stem console, the
per-tool audio registry with its `analyze`/`apply` contract, per-step tunable cleaning, search
ranked on what a song *is* (with "why did this match" explanations), and the fix picker offering
every DSP tool rather than only the four with detectors. Issues #82 and #86 notified.

Sanity gate ran fully this time: `bigflavor-backend` restarted to `Application startup complete`
and healthy, and `npm run build` compiled the frontend clean. Note that PR #90 (pitch/click
detection, issue #89) was approved but **not merged** at tag time, so it is *not* in v0.17.0 — it
lands in the next release.

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
