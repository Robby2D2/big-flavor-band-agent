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
