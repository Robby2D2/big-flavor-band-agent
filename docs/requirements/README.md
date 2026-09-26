# Functional Requirements — Big Flavor Band Agent

This directory is the **product contract** for the app: what it does, and the specific behaviors that
must always hold. Anyone — a person or an agent — should be able to read these files and understand
what the product promises, without reading the code.

**Mission.** Make it effortless to **discover, play, and produce** music from the Big Flavor Band's
~1,300-song catalog.

Requirements answer *"what must always be true for a user?"*. OKRs (`.agents/OKRS.md`) answer
*"what are we trying to move?"*. A requirement is not a goal, a metric, or a backlog item — it is a
promise the product already makes and must keep.

---

## The areas

| Area | File | Covers |
|------|------|--------|
| Catalog & data | [catalog.md](catalog.md) | Songs, metadata, lyrics, indexes, ingest |
| Search & discovery | [search.md](search.md) | All search modes, results, playback from results |
| AI agent & DJ | [agent-dj.md](agent-dj.md) | Chat, DJ requests, playlist generation, grounding |
| Radio | [radio.md](radio.md) | The live stream, queue, transport controls |
| Production & editing | [production.md](production.md) | Analysis, cleanup, versions, stems, lyric editing |
| Recording sessions | [sessions.md](sessions.md) | Reaper session upload, take detection, staging |
| Accounts & access | [accounts.md](accounts.md) | Sign-in, roles, invites, admin |
| Platform | [platform.md](platform.md) | LLM provider, BFF boundary, responsiveness, deploy |

---

## How to read a requirement

Every requirement has a stable ID, a **MUST** statement, and (where it isn't obvious) a *Why*.

> **SRCH-04** — A search result MUST be playable directly from the result list, without navigating
> away from the results.
> *Why:* finding the song is only half the job; hearing it is the point.

- **MUST** — an invariant. Breaking it is a regression, whatever else the change achieves.
- **MUST NOT** — a behavior the product is not allowed to have.
- Requirements describe **observable behavior**, never implementation. No file, class, endpoint, or
  library names.

**Known gaps.** A requirement that the code does not currently satisfy stays in the file and is
marked inline:

> ⚠️ **Known gap (2026-09-26):** …what is actually true today, and where it's tracked.

A gap is a bug against the contract, not a licence to ignore it.

---

## IDs are permanent

`AREA-NN` — `SRCH-04`, `RAD-02`. The number is assigned once and **never reused or renumbered**, so
an issue, spec, PR, or comment can cite `SRCH-04` years later and still mean the same promise.

- New requirement → next unused number in that file, appended to its subsection.
- Retired requirement → leave the line, prefix it **~~RETIRED~~**, and say what replaced it and when.
- Requirement moves areas → keep the old ID as a pointer line; don't renumber.

---

## Changing a requirement

Requirements change through the normal issue → spec → PR flow, so every change gets a human merge.

1. **The product-manager agent authors the change.** When a greenlit issue adds or alters a promise,
   the PM's spec carries a **Requirements impact** section with the exact requirement text and its
   target file.
2. **The developer commits it in the same PR as the code.** A PR that changes user-facing behavior
   covered by this directory updates the requirement in that PR — code and contract land together.
3. **QA checks the two match**, and that the change doesn't break any requirement the spec cites.
4. **A human merges.** That merge is the approval.

Small corrections — a requirement that was always true but never written down, a typo, a stale
"known gap" — can be committed directly by anyone.

---

## Conflicting with a requirement is a stop, not a trade-off

If doing what an issue asks would **break** a requirement here, that is not a normal scoping call.

- The product-manager agent **stops**, posts a `requirements-conflict` comment naming the exact ID
  and the contradiction, labels the issue `requirements-conflict` + `awaiting-answer`, and does not
  mark it `dev_ready`.
- **A human must confirm in the issue thread** before any work starts. No agent may overrule a
  requirement on its own reasoning, however good the reasoning is.
- If the human confirms, the spec must include the requirement amendment (retire it, narrow it, or
  replace it) so the contract and the code stay honest.

This should be rare. Most issues that look like conflicts are really gaps in the requirement's
wording — say so, and propose the clarified wording instead.
