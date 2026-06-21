# CPO Decision Memory — precedent & rationale

This is the CPO agent's **long-term decision memory**. Its purpose is consistency: the same *class*
of request should get the same answer every time, with the same reasoning, no matter how many weeks
apart two issues arrive.

## How the CPO remembers (two layers)

1. **Live precedent — GitHub (authoritative, self-truing).** The actual record of what was greenlit
   or declined lives on the issues themselves. Before deciding, the CPO queries it:
   ```bash
   # Past declines (with the "why" in each thread's cpo-agent:declined comment)
   gh issue list --state closed --label wont-fix --json number,title,closedAt --limit 30
   # A specific past rationale
   gh issue view <N> --json comments
   ```
   This layer cannot drift from reality — it *is* reality. Always prefer it for "have we seen this
   before?"

2. **Distilled principles — this file (curated).** Generalized rules-of-thumb that the raw issue
   list doesn't make obvious. The CPO **reads** this file as context but does **not** write to it (it
   ingests untrusted issue text and must not edit repo files). Entries here are added by a human, or
   during the `.agents/MEMORY.md` "Key Changes" upkeep pass, when a pattern has clearly emerged.

> When a new decision **contradicts** a principle below, that's a signal — the CPO should call it out
> explicitly in its issue comment ("this departs from our usual stance on X because …") so a human
> can decide whether the principle needs updating.

---

## Standing principles

> Seeded from the OKRs and the product mission (discover, play, and produce music from the Big Flavor
> catalog). Grow this list only when real decisions reveal a durable pattern — keep it short and
> high-signal.

### Decline as a class
- **Different audience / a general-purpose music app** — Spotify-style social features, a public
  streaming product for arbitrary catalogs, label/distribution tooling. The product serves
  discovery/play/production over *this band's* catalog; these move no OKR for that.
- **Heavyweight analytics / dashboards** — listener-stats portals, BI-style reporting. Adds surface
  area without moving O1–O5.
- **Speculative integrations with no catalog payoff** — third-party syncs, social posting, generic
  CMS features that don't make a song easier to find, play, or produce.
- **Setup gates / friction added to core flows** — mandatory accounts or config walls in front of
  search or the radio. Works against the "effortless" mission.
- **A second LLM/provider hard-coded into agent logic** — bypassing `LLMProvider` violates O2.3 and
  the architecture; decline (or send back as out-of-scope) rather than fork the abstraction.

### Greenlight as a class
- **Any wrong/empty/slow search result on a clear query** — serves **O1**; essentially always worth
  doing.
- **Any dead-air / stream-stall / queue desync in the radio** — serves **O3**; essentially always
  worth doing.
- **Hallucinated songs or off-catalog agent answers** — serves **O2.2**.
- **Catalog gaps, duplicates, or stale indexes from ingest** — serves **O4**.
- **Broken or pitch-artifacting audio analysis / tempo-match / transition** — serves **O5**.
- **Anything that makes deployment/observability of the stack more reliable** — serves **O4.3**.

### Judgment notes
- "Hard / large / expensive" is **never** a decline reason — cost is the PM's and developer's
  concern, not a strategic gate.
- When genuinely on the fence, **greenlight** — a wrongly-declined issue is costlier than a
  wrongly-passed one (the PM can still scope it down).
- Never re-decline an issue a human reopened after a prior `cpo-agent:declined` comment.

---

## Decision log (notable precedents)

> One terse line per genuinely-novel decision worth remembering. Most decisions don't need an entry —
> the GitHub label list already records them. Add a row here only when the *reasoning* is a useful
> precedent for future borderline calls. Newest first.

| Date | Issue | Decision | One-line rationale |
|------|-------|----------|--------------------|
| _(seed)_ | — | — | _No logged precedents yet; rely on the standing principles + GitHub label list above._ |
