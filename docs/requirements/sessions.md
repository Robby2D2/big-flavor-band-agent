# Recording Sessions — Functional Requirements

Prefix **SESS**. See [README.md](README.md) for how to read, cite, and change these.

The band records whole rehearsals and the songs have to be found inside the result. Detection is
knowingly fallible, so every promise here is built around **a human deciding what's real**.

Access: editor-gated — see [accounts.md](accounts.md).

---

## Upload

**SESS-01** — A producer MUST be able to upload a whole recording session — multi-gigabyte, many
tracks — from the browser, without splitting it by hand.

**SESS-02** — An upload MUST survive an interrupted or retried transfer without corrupting the
result.

**SESS-03** — Upload progress MUST be visible.

---

## Detection

**SESS-04** — Scanning a session MUST produce **candidate takes** — stretches the band was playing a
song — for a human to review.

**SESS-05** — Detection MUST be treated as fallible. The product MUST NOT act on a detected take as
though it were confirmed.

**SESS-06** — A scan MUST narrate what it is doing and how far it has got, and that narration MUST
survive a page reload.
*Why:* a scan runs for tens of minutes; a reload must not lose the story.

**SESS-07** — A scan that cannot read part of a session — missing media, an unreadable track — MUST
skip it and say so, not fail the whole run.

---

## Review

**SESS-08** — A producer MUST be able to audition each detected take, see its waveform, and hear its
individual tracks.

**SESS-09** — A producer MUST be able to **discard** a take that isn't a song. Discarding MUST be
reversible — it marks the take, it does not delete it.

**SESS-10** — Nothing from a session MUST reach the catalog without a human importing it. Detected
takes are staged, not published.

**SESS-11** — The band's own track names MUST be preserved through detection and rendering, so a
producer recognizes their own session.
