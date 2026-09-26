# AI Agent & DJ — Functional Requirements

Prefix **DJ**. See [README.md](README.md) for how to read, cite, and change these.

The agent is the plain-language way in: ask for music or ask about the catalog, get something
playable or something true.

---

## Conversation

**DJ-01** — A user MUST be able to ask for music and information in plain language and get an
answer, without learning commands or filters.

**DJ-02** — Agent responses MUST stream as they are produced, so a long answer starts appearing
quickly rather than arriving all at once.

**DJ-03** — When the agent fails — model unreachable, tool error, timeout — it MUST tell the user
plainly. It MUST NOT return a fabricated answer in place of a failure.

---

## Grounding

**DJ-04** — Every song the agent names, recommends, or queues MUST be a real song in the catalog
(OKR **KR2.2**). Hallucinated titles are a defect, never an acceptable near-miss.

**DJ-05** — When the agent makes a claim about a song — its tempo, key, mood, lyrics — that claim
MUST come from the catalog's own data, not from the model's general knowledge.

**DJ-06** — The agent MUST NOT present a song it could not find as one it found. "I couldn't find
that" is a correct answer.

---

## DJ requests and playlists

**DJ-07** — A DJ request MUST return a **coherent, playable queue in one ask** (OKR **KR2.1**) —
"an upbeat 30-minute set", "songs like X" — without the user refining it turn after turn.

**DJ-08** — A DJ request that names a constraint the user can check — a length, a mood, a
similarity — MUST honor it, or say which part it could not honor.

**DJ-09** — A generated playlist MUST be reviewable before or as it plays: the user can see which
songs were chosen.

**DJ-10** — The agent MUST be able to act on the radio (queue, skip, play, pause) when asked, with
the same effect as doing it by hand (**RAD-07**).
