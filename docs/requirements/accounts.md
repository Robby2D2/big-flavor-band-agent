# Accounts & Access — Functional Requirements

Prefix **ACCT**. See [README.md](README.md) for how to read, cite, and change these.

Three roles: **listener**, **editor**, **admin**. Listening and searching are open to anyone signed
in; changing the catalog is not.

---

## Sign-in

**ACCT-01** — A user MUST be able to sign in with Google, with no separate password to manage.

**ACCT-02** — Anyone who signs in MUST get the **listener** role by default. No new sign-in is ever
an editor or an admin.

**ACCT-03** — A session MUST NOT be forgeable. A user MUST NOT be able to claim another user's
identity or role by editing anything the browser holds.

**ACCT-04** — Authorization MUST **fail closed**: a role that cannot be determined is a refusal, not
a pass.

---

## Roles

**ACCT-05** — **Listener** MUST be able to search, play songs, listen to the radio, add songs to the
queue, and remove a queued song **they added themselves**.

**ACCT-06** — **Editor** MUST additionally be able to reach the edit, produce, and recording-session
surfaces.

**ACCT-07** — **Admin** MUST additionally be able to see all users, change roles, and manage
invites.

**ACCT-08** — A destination the user's role may not use MUST NOT be offered to them in navigation.

**ACCT-09** — A user who reaches a surface their role may not use MUST be told plainly, not shown a
broken or empty page.

**ACCT-15** — Skipping the current song, pausing or resuming the stream, and removing a queued song
the user did not add themselves MUST be restricted to **editor** and **admin**, MUST NOT be offered
to a listener, and MUST be refused where the action is carried out rather than only hidden in the
interface.

---

## Invites

**ACCT-10** — An admin MUST be able to promote someone to **editor** by issuing an invite link,
without editing the database.

**ACCT-11** — An invite MUST be single-use, time-limited, revocable, and **bound to the invited
email address** — a forwarded link grants nothing.

**ACCT-12** — Only **editor** MUST be invitable. Admin stays a deliberate promotion by an existing
admin.

**ACCT-13** — An invite link MUST be shown exactly once, at creation, and MUST NOT be recoverable
afterwards.

**ACCT-14** — An expired, revoked, or already-used invite MUST say what happened when opened.
