# Long-Term Memory — Big Flavor Band Agent

This file is a table of contents. Each entry links to a topic-specific file in `.agents/memory/`.
Add a row when you move an older `MEMORY.md` entry into its own topic file, or when you distill a
durable pattern worth its own page.

---

| Date | Topic | File | Summary |
|------|-------|------|---------|
| 2026-06-19 | CPO decision memory | [memory/cpo_decisions.md](memory/cpo_decisions.md) | CPO agent's precedent + standing principles for greenlight/decline consistency. Two layers: GitHub `wont-fix` label trail (authoritative) + curated principles. Agent reads, never writes. |
| 2026-06-19 | PM spec conventions | [memory/pm_conventions.md](memory/pm_conventions.md) | Product-manager terminology table, required spec structure, success-metric→OKR alignment, recurring out-of-scope boundaries. Agent reads, never writes. |
| 2025-11-24 | Radio streaming | [memory/radio_streaming.md](memory/radio_streaming.md) | Icecast + Liquidsoap architecture; the `mksafe()` and playlist-path-rewrite invariants; how the backend drives the stream via `radio.m3u`. |
| 2025-11-10 | Search & RAG | [memory/search_rag.md](memory/search_rag.md) | Text / lyric / audio-similarity / tempo / hybrid search; pgvector; Whisper large-v3 lyrics; sentence-transformers; READ-vs-WRITE split. |
| 2025-11-09 | Catalog scraping & ingest | [memory/scraping.md](memory/scraping.md) | bigflavor.com scrape, de-duplication, audio+metadata indexing, incremental "process only missing" mode. |
| 2026-08-01 | Release history | [memory/releases.md](memory/releases.md) | Every `vX.Y.Z` release-manager cut, v0.1.0 → v0.16.2 — routine version-bump entries, low ongoing signal once shipped. |
| 2026-08-01 | Early history & one-off fixes | [memory/history_2025_2026.md](memory/history_2025_2026.md) | 2025-11 project-genesis timeline (reconstructed from git) + two 2026-06 incident writeups (null-metadata back-fill, the `/produce` Analyze silent-no-op bug). |
