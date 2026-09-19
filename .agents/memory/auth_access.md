# Auth & Access — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) on 2026-09-18 to keep the rolling file under ~200 lines.
How someone becomes an editor, and what guards the session. Newest first.

The companion entry below — signing the `appSession` cookie and closing the two unguarded user
routes — closed the holes the invites entry's "Still open" note named. Moved here from
[MEMORY.md](../MEMORY.md) on 2026-09-19.

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
