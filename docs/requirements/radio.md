# Radio — Functional Requirements

Prefix **RAD**. See [README.md](README.md) for how to read, cite, and change these.

The radio is a single live stream that everyone hears together. Its one unbreakable promise is that
it keeps playing.

---

## The stream

**RAD-01** — The radio MUST be a **single shared stream**: every listener hears the same song at the
same point at the same time. It is not a per-user player.

**RAD-02** — The stream MUST NOT fall to silence while there are playable songs available to it
(OKR **KR3.1**). If the queue empties, it falls back to catalog music, never to dead air.

**RAD-03** — A listener MUST be able to start listening from the radio page with no setup beyond
pressing play.

**RAD-04** — Radio state — the current song, the queue, play/pause, and position — MUST survive a
backend restart without a human intervening to recover it (OKR **KR3.3**).

**RAD-05** — The radio page MUST show what is playing now — including when the stream is playing
fallback catalog music — and what is queued next, and MUST keep that display in agreement with the
audio actually on the air as the stream advances.

---

## Queue and transport

**RAD-06** — A user MUST be able to **add a song to the queue** from search results and from the
radio page.

**RAD-07** — An **editor** or **admin** MUST be able to **skip** the current song, **remove any
queued song**, and **play/pause**. A **listener** MUST be able to remove a queued song they added
themselves (**ACCT-05**), and adding to the queue stays open to any signed-in user (**RAD-06**).

**RAD-08** — A queue action MUST be reflected in the live stream within a few seconds (OKR
**KR3.2**), and in the on-screen queue immediately.

**RAD-09** — A queue action that cannot be carried out MUST tell the user it failed. It MUST NOT
silently appear to succeed.

**RAD-10** — Skipping the last queued song MUST leave the stream playing (see **RAD-02**), not stop
it.

**RAD-13** — The queue MUST remember which user added each song, and that attribution MUST survive a
backend restart with the rest of the radio state (**RAD-04**). A queued song with no recorded adder
MUST be treated as nobody's own: only an **editor** or **admin** may remove it.

---

## Asking the DJ

**RAD-11** — A user MUST be able to shape the radio in plain language — "play something mellow",
"add three upbeat songs" — and have the queue change accordingly. See [agent-dj.md](agent-dj.md).

**RAD-12** — Songs the DJ queues MUST be real catalog songs that will actually play (**DJ-04**).
