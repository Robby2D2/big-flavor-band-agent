# Platform — Functional Requirements

Prefix **PLAT**. See [README.md](README.md) for how to read, cite, and change these.

Cross-cutting promises that no single feature owns, but every feature depends on.

---

## The LLM is swappable

**PLAT-01** — The LLM provider MUST be selectable by configuration — local Ollama or hosted
Claude — **with no change in user-facing behavior** (OKR **KR2.3**).

> ⚠️ **Known gap (2026-09-26):** the hosted Anthropic path cannot currently make a call, so the
> agent, DJ, and search-explain features work only on the local provider. Recorded in
> `.agents/ARCHITECTURE.md` → "`AnthropicProvider` cannot make a call".

**PLAT-02** — Switching providers MUST NOT require a user to relearn anything or lose a capability.
If a capability genuinely cannot be provided by one backend, that MUST be stated, not silently
dropped.

---

## Access boundary

**PLAT-03** — Anything the browser can reach MUST pass through an authenticated path. A protected
action MUST NOT be reachable by calling the backend directly.

> ⚠️ **Known gap (2026-09-26):** the search and agent routes (and part of radio) are not yet behind
> the service check. They are read-mostly, but the boundary is incomplete.

**PLAT-04** — A feature the browser calls MUST actually be wired end-to-end. A missing route MUST
NOT surface to the user as an empty-looking feature.

---

## The interface

**PLAT-05** — Every user-facing surface MUST be usable on a phone. A feature that only works on a
desktop viewport is incomplete.

**PLAT-06** — The interface is **dark-only**. There is no light mode and no theme toggle; new
surfaces MUST use the Console design tokens.

**PLAT-07** — An action that takes noticeable time MUST show that it is working, and an action that
fails MUST say so in language the user can act on.

**PLAT-08** — A user MUST NOT lose work to a page reload. Long-running work reports its own state
(see **PROD-11**, **SESS-06**).

---

## Operability

**PLAT-09** — The stack MUST deploy to production from a documented, repeatable process (OKR
**KR4.3**).

**PLAT-10** — A failure MUST be diagnosable from logs — what failed, on which song or request, and
why.

**PLAT-11** — Secrets MUST come from configuration, never from committed source.

**PLAT-12** — The system MUST come back up on its own after a restart, with no manual step to
recover user-visible state (see **RAD-04**).
