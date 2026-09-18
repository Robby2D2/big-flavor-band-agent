# Auth & Access — Big Flavor Band Agent

Moved out of [MEMORY.md](../MEMORY.md) on 2026-09-18 to keep the rolling file under ~200 lines.
How someone becomes an editor, and what guards the session. Newest first.

The companion entry — signing the `appSession` cookie and closing the two unguarded user routes —
is still in [MEMORY.md](../MEMORY.md); it closed the holes this entry's "Still open" note named.

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
