# Frontend BFF Routes & the Proxy Layer — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) on 2026-09-18 to keep the rolling file under ~200 lines.
Two entries about the layer between the browser and FastAPI: the `app/api/` route handlers the
browser must go through, and the proxies in front of them. Both were failures that *looked* like
application bugs and were not. Newest first.

The standing lesson across both: **only `/api/agent/*` is proxied by a `next.config.js` rewrite**, so
every other backend path the browser calls needs its own handler under `frontend/app/api/`, and any
body that doesn't parse as JSON came from a proxy rather than from this app.

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
