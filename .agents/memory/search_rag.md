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
- **Vector storage** is pgvector in PostgreSQL; SQL search functions live in `database/sql/`
  (`init/` + `migrations/`). `database/update_search_functions.sql` was retired in issue #114.

## Design rule

**READ/search = RAG library (in-process, fast). WRITE/production = MCP server (separate process).**
This split was deliberately hardened over several commits (`cb57406`, `72d7816`, `36e8f74`). Keep
search code in `src/rag/` and production/write code in `src/production/`; don't blur them.

## UI note

The frontend deliberately shows **raw structured results**, not the agent's prose narration
(`eb3a032`, 2025-11-23) — clearer for music discovery.

---

## Later entries (moved from MEMORY.md, 2026-10-15)

*The entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-10-15 prune.*

### 2026-09-28 — Three broken search functions retired rather than repaired (issue #114)
`search_by_tempo_and_audio`, `search_songs_hybrid` and `search_similar_songs_by_text` had raised on
*every* call since migration `04` (`song_id VARCHAR(50)` against an integer; the two text-side ones also
referenced `te.text_embedding`, gone since text embeddings moved to all-MiniLM-L6-v2). The owner's call
was **delete, don't fix** — "if it turns out we need them in the future, we can always add them back
in". Migration `22` drops all three by signature; their three uncalled `SongRAGSystem` methods
(`search_by_text`, `search_hybrid`, `search_by_tempo_and_audio`) are gone, as are
`database/update_search_functions.sql`, `database/apply_search_update.py` and
`tests/update_search_functions.ps1`.

- **Absence of a caller is the whole justification, so it is the thing to verify — not the test run.**
  Every SRCH-02 mode is served by a *different*, working path (`search_by_text_description`,
  `search_lyrics_by_keyword`, `search_by_tempo_range`, `search_text_with_tempo`,
  `search_similar_songs_by_audio`), which is why deleting these breaks nothing. Confirmed by measuring
  all five endpoints plus `/api/songs/{id}/related` live after the drop, not by reading the code.
- **The trap is name collisions, and there were three layers of them.** `src/api/routers/search.py`
  has *route handlers* named `search_by_text` and `search_hybrid`; `src/agent/big_flavor_agent.py`,
  `src/api/research_jobs.py` and `src/rag/deep_search.py` carry an agent *tool* called `search_hybrid`
  that dispatches to `_perform_hybrid_search`; and `tests/rag_mcp_server.py` has its own `search_hybrid`
  composing working methods. All four are live and all four stay. **Delete by call graph, never by name.**
- **A hand-run SQL file that re-creates functions can silently undo a migration, and this one would
  have.** `update_search_functions.sql` still carried the pre-migration-`20` `song_id VARCHAR(50)`
  declaration for `search_similar_songs_by_audio`, so re-applying it would have re-broken the mode PR
  #113 had just fixed. Retiring the file *is* the fix; migrations are the only path.
- **A dead function is worse than dead code**: it looks available, and the first caller discovers it
  is not. Nothing reported any of this for ten months (the same blind spot as **CAT-12**). A smoke
  check that every remaining search function answers was deliberately left to its own issue.
- `tests/test_rag_hybrid_dimensions.py` went with `search_hybrid` — all three of its tests covered only
  that method's placeholder-vector behavior, so no coverage of anything that still exists was lost
  (746 → 743 passing, same 13 pre-existing failures).
- **Migrations `21` and `22` are both unapplied in production.** `22` is applied on the dev stack.

### 2026-09-27 — Audio similarity had never used CLAP, and the "one-word fix" was three (issue #111)
`clap_embedding` was NULL for all 1,415 rows back to 2025-11-09, so every `combined_embedding` was the
librosa fallback and "find me more like this" ranked on recording texture. Reported in #107, fixed
here. **Measured on the live stack before writing anything, and the issue's premise was too small** —
full detail in [ARCHITECTURE.md](ARCHITECTURE.md); the three findings are:

- `clap_processor(audios=)` → `audio=` is only the first break. transformers 5's
  `get_audio_features()` returns a `BaseModelOutputWithPooling`, not a tensor, so the kwarg fix alone
  died on `'BaseModelOutputWithPooling' object has no attribute 'cpu'`. The embedding is its
  `pooler_output`. **Distrust a one-word fix to dependency drift** — a rename rarely moves one thing.
- **A working CLAP vector did not fit the column.** The combined representation is 37 librosa dims +
  512 CLAP = **549**; `init/03` said so and migration `04` re-created the table at `vector(512)`,
  unnoticed for ten months because CLAP never produced a vector to store. Shipping only the kwarg fix
  would have failed *every* insert. Migration `19` restores 549, guarded on `atttypmod` so a re-run
  cannot wipe the rebuilt vectors.
- **The report was the third bug and the reason this lasted.** `index_audio_file` stored a CLAP-less
  row and returned `True`, so a batch said `{'total': 74, 'success': 74, 'failed_files': []}` with zero
  CLAP embeddings in it — #107's lesson one level up: there a blanket `except` turned an error into
  missing data, here the *caller* turned missing data into a success. New **CAT-12** forbids it, and
  the guard sits at the one seam so the scrapers, batch indexer and produce approval all inherit it.

**Mixed embedding spaces are now prevented structurally, not by discipline** (new **CAT-11**): a
fallback vector is 512 wide and a CLAP one 549, so they cannot share the column, and a not-yet-rebuilt
row is NULL, which the search functions' `>=` threshold drops. The rebuild therefore compared a
growing *subset*, every comparison CLAP-vs-CLAP — never an error, never two spaces. The rejected
alternative (staging column + atomic cutover) keeps coverage whole but leaves `index_audio_file` not
knowing which column is live, breaking the incremental path (**CAT-08**) for the same window.

`scripts/reindex_audio_embeddings.py` **updates rows and never inserts them**: `audio_embeddings` is
unique on `audio_path` and 1,341 rows still held a host-written Windows relative path that cannot open
in the container, so upserting on a freshly resolved path would have created a second row per song and
returned each twice (**CAT-04**/**CAT-07**). Resumable by construction (a row with both halves is
done), and it refuses to run where CLAP is unavailable.

**How bad the fallback was:** 475 of its 512 dims are zeros, so the whole catalog sat in a
37-dimensional cone and every pair scored **0.994-1.000** similar. Ranking was noise in the fourth
decimal.

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
