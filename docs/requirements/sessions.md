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

**SESS-16** — Where the band's Google Drive is connected, a producer MUST be able to import a session
straight from its project folder there, without downloading it or building a zip. The transfer runs
on the server and its progress MUST be visible the way a scan's is (**SESS-06**); it MUST NOT depend
on the producer's browser staying open.
*Why:* the sessions already live on Drive; moving gigabytes down to a laptop and back up is the whole
cost the feature removes.

**SESS-17** — An imported file MUST be whole before a scan reads it: an interrupted download MUST
resume or fail the import, never be scanned as a truncated track. The same Drive folder MUST NOT be
imported twice at once, and the import list MUST show which folders already have a session.

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

**SESS-12** — A name generated for a detected take MUST be no more than six words, and MUST be drawn
from what that take actually contains rather than invented. A take with no words of its own MUST be
labelled as having none, not given a made-up title.

**SESS-13** — Takes that are attempts at the same song MUST be presented as a single group, and each
take inside a group MUST stay individually visible, auditionable, and distinguishable from its
siblings.

**SESS-14** — Every detected take MUST remain visible in review whether or not it was grouped. A take
the product cannot confidently assign to a song MUST be shown on its own, never hidden, merged away,
or dropped.
*Why:* a grouping guess that loses a take loses recorded material.

**SESS-15** — A group of takes MUST start with no keeper chosen, and the product MUST NOT choose one
for the producer. Until a human chooses, nothing from that group is eligible to reach the catalog
(**SESS-10**).
