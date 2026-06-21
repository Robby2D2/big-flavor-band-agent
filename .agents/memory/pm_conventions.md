# PM Spec Conventions — terminology & spec patterns

This is the product-manager agent's **long-term convention memory**. Its purpose is consistency: two
specs written weeks apart should use the same words, the same structure, and draw the same scope
boundaries — so the developer and QA agents see a stable target.

## How the PM remembers (two layers)

1. **Live precedent — GitHub (authoritative, self-truing).** Past specs live on the issues. Before
   writing a new spec, the PM can skim recent ones for wording and structure to match:
   ```bash
   gh issue list --state all --label dev_ready --json number,title --limit 20
   gh issue view <N> --json comments
   ```

2. **Distilled conventions — this file (curated).** The terminology and patterns below. The PM
   **reads** this file as context but does **not** write to it (it ingests untrusted issue text and
   must not edit repo files). Entries are added by a human, or during the `.agents/MEMORY.md` "Key
   Changes" upkeep pass, when a convention has stabilized.

---

## Terminology (use these exact words in specs)

| Use | Not | Note |
|-----|-----|------|
| **catalog** | library, database, collection | The ~1,300 Big Flavor songs. |
| **song** | track, record, tune | The core entity. Has metadata, lyrics, audio embeddings. |
| **search** (text / lyric / audio-similarity / tempo / hybrid) | query, lookup | Name the mode. |
| **agent** / **AI DJ** | bot, assistant, chatbot | The LLM orchestration; "DJ" for playlist/queue asks. |
| **queue** | playlist (for radio) | The ordered set of songs the radio will play next. |
| **radio** / **stream** | broadcast, channel | The continuous Icecast/Liquidsoap audio stream. |
| **embedding** | vector, feature | pgvector representation (audio CLAP / text). |
| **ingest** / **scrape** | import, crawl | Getting catalog data from bigflavor.com into Postgres. |
| **production tools** | effects, processing | Analyze / tempo-match / transition / master (MCP server). |
| **LLM provider** | model backend | The Ollama/Anthropic abstraction (`LLMProvider`). |

## Spec conventions

- **Always use the exact spec template** in `.claude/agents/product-manager.md` Step 4 (Problem /
  Value / Goal / Success metrics / Acceptance criteria / Out of scope). Don't reorder or rename
  headings — QA and the developer key off them.
- **Success metrics must tie to an OKR KR** where possible (see `.agents/OKRS.md`). Prefer the KR's
  own threshold (e.g. "search returns in ≤3s" for O1.1; "stream never falls to `blank()`" for O3.1).
- **Acceptance criteria are observable behaviors**, phrased as checkable bullets ("A lyric search for
  X returns song Y in the top 3", "After skip, the stream advances within N seconds"). Never
  implementation detail (no file/class/function names).
- **"Out of scope" is required** on every spec — name at least one thing this issue is *not* doing,
  to keep the developer's change tight.
- **Respect the architecture seams** when scoping: search/read work lives in the RAG system, write/
  production work in the MCP server, and all LLM calls go through `LLMProvider`. If a request would
  cross those seams, call it out in the spec.
- **Mission fit is already settled** by the CPO before the PM sees the issue. Do not re-argue whether
  it belongs in the product; spec the greenlit intent.

## Recurring out-of-scope boundaries

> Common things to explicitly exclude so specs don't balloon. Grow as patterns recur.

- A different/general music catalog or audience (CPO declines — shouldn't reach the PM).
- New LLM providers wired directly into agent logic (must go through `LLMProvider`, not around it).
- Heavyweight analytics/dashboards beyond what a discovery/DJ/production flow needs.
- Re-scraping or re-indexing the whole catalog when an incremental "process only missing" path
  already exists — prefer the incremental path unless the issue is specifically about a full re-index.
