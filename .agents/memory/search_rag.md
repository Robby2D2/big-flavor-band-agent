# Search & RAG

*Reconstructed 2026-06-19 from commits across 2025-11-06 → 2025-11-21 (`41180f4` created the RAG
system; `9becb30` title similarity; `96ce1b5` lyric matching; `09bb7ba` Whisper large-v3;
`3a4145c` full lyric + semantic search; `c41f90c` search tuning).*

## What it is

`SongRAGSystem` (`src/rag/big_flavor_rag.py`) is the **read/search path**, called **directly** by the
backend as a library (not a service) for speed. Backend search routes (`/api/search/natural`,
`/api/search/text`, `/api/search/lyrics`, `/api/songs/{id}/lyrics`) hit it without an LLM round-trip.

## Search modes

- **Text / natural-language** — `sentence-transformers` embeddings over metadata.
- **Lyric** — full-text **and** semantic (embedding) lyric search combined (`3a4145c`).
- **Audio similarity** ("sounds like") — CLAP + librosa audio embeddings
  (`src/rag/audio_embedding_extractor.py`), stored as pgvector.
- **Title similarity** (`9becb30`).
- **Tempo / BPM**.
- **Hybrid** — combine the above.

## Data pipeline

- **Lyrics** are transcribed with **Whisper large-v3** (`lyrics_extractor.py`, indexed via
  `index_lyrics.py`); the model was upgraded to large-v3 for accuracy (`09bb7ba`), with GPU testing
  tooling added at the same time.
- **Vector storage** is pgvector in PostgreSQL; SQL search functions live in `database/sql/` and
  `database/update_search_functions.sql`.

## Design rule

**READ/search = RAG library (in-process, fast). WRITE/production = MCP server (separate process).**
This split was deliberately hardened over several commits (`cb57406`, `72d7816`, `36e8f74`). Keep
search code in `src/rag/` and production/write code in `src/production/`; don't blur them.

## UI note

The frontend deliberately shows **raw structured results**, not the agent's prose narration
(`eb3a032`, 2025-11-23) — clearer for music discovery.

---

## Later entries (moved from MEMORY.md, 2026-09-18)

### 2026-09-15 — Search accuracy was never the LLM's fault
Complaint: results are poor and search is slow. The assumption was the local model. Measured first:
`/api/search/text` (no LLM) and `/api/search/natural` (agent) returned **byte-identical ordering and
scores** — 0.483, 0.449, 0.430, 0.426, 0.413 — in 0.04s and 11.6s respectively. `search_songs`
calls `search_by_text_description` directly and then only asks the LLM to write a sentence per
result. The model contributed nothing to ranking and 100% of the latency.

Three real defects, all in the SQL:
1. **Only lyrics were embedded.** `text_embeddings` held 1,338 rows, all `content_type='lyrics'`.
   Genre, mood and energy were invisible to semantic search.
2. **The keyword branch used the whole query as one `ILIKE '%…%'`**, so any multi-word query matched
   nothing lexically.
3. **Keyword hits scored a flat 0.5**, replacing the semantic score. Searching `punk` returned five
   songs at *exactly* 0.500, tie-broken alphabetically — no relevance ordering at all.

Fixes:
- **`src/rag/search_text.py`** (pure, unit-tested): `build_metadata_text` renders title/genre/mood/
  energy/tempo/key as a labelled sentence to embed; `tokenize_query` splits the query, drops
  request-describing stop words ("find me some songs"), keeps apostrophes (so "don't" never becomes
  "don" and substring-matches London), and splits on `_` because underscore is a single-character
  **ILIKE wildcard**.
- **`scripts/backfill_metadata_embeddings.py`** — one `metadata` row per song, batched on GPU.
  1,341 songs in seconds. Idempotent; re-run after any metadata change.
- **Scoring is now `semantic + keyword_bonus`**, capped at 1.0. First attempt made keyword a rival
  score (`GREATEST` + a fraction of `LEAST`) and it was *worse*: a lone title substring outranked
  genuine matches, Country Roads fell to 5th for "upbeat country song about home", and everything
  compressed into 0.744-0.743. As a bonus (0.10 per controlled-vocabulary hit, 0.05 per title
  substring, capped 0.30) semantic leads and Country Roads returns to 1st at 0.638 with clear air.
- Every candidate is scored semantically **even when it surfaced only via keywords** — otherwise
  same-genre songs all tie on the bonus and fall back to alphabetical.

Results now: `punk` → all punk, 0.664→0.651 differentiated. `high energy rock` → all rock/high,
0.808 top. Search 26-60ms.

**Explanations moved to `/api/search/explain`** (`src/rag/explain.py`), one song, on click. The old
per-result commentary was ungrounded — it captioned a catalogue cover of "Country Roads" with an
invented claim that Bob Dylan wrote it under a pseudonym, and the leading `": "` showed the JSON
parse had failed and fallen back to slicing fragments. The new prompt supplies only that song's own
facts and forbids inventing authorship or history. Grounded output, 0.3-0.7s warm, and it blocks
nothing. Full BFF round-trip: search 0.16s (was 2-12s), explain 0.72s on click.

Verified no regressions by diffing the full pytest failure set against a `git stash` baseline:
13 before, 13 after, identical — all stale demo scripts calling methods that no longer exist
(`SongRAGSystem.initialize`, `DatabaseManager.disconnect`).
