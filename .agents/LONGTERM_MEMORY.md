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
| 2026-09-18 | Search & RAG | [memory/search_rag.md](memory/search_rag.md) | Text / lyric / audio-similarity / tempo / hybrid search; pgvector; Whisper large-v3 lyrics; sentence-transformers; READ-vs-WRITE split. Plus the 2026-09 accuracy rework: metadata embeddings, query tokenization, keyword-as-*bonus* scoring, and explanations moved off the search path. |
| 2025-11-09 | Catalog scraping & ingest | [memory/scraping.md](memory/scraping.md) | bigflavor.com scrape, de-duplication, audio+metadata indexing, incremental "process only missing" mode. |
| 2026-08-01 | Release history | [memory/releases.md](memory/releases.md) | Every `vX.Y.Z` release-manager cut, v0.1.0 → v0.16.2 — routine version-bump entries, low ongoing signal once shipped. |
| 2026-09-18 | Produce / stem console | [memory/produce_console.md](memory/produce_console.md) | The `/produce` per-tool API (declare-params → analyze → apply), the Claude Design "Console" redesign, the per-stem review queue, instrument tagging, timed-lyrics phase 1, the Start-analysis stem-reuse rule, and the waveform-peaks rework that cut a tab open from 262 MB to 11 MB. |
| 2026-08-01 | Early history & one-off fixes | [memory/history_2025_2026.md](memory/history_2025_2026.md) | 2025-11 project-genesis timeline (reconstructed from git) + two 2026-06 incident writeups (null-metadata back-fill, the `/produce` Analyze silent-no-op bug), plus the 2026-07 pipeline-concurrency standards. |
| 2026-09-18 | Deployment & ops | [memory/deploy_ops.md](memory/deploy_ops.md) | What a production deploy here actually is (same compose file, same Postgres volume, so prod *is* the dev database) and what bites at deploy time — `npm ci` strictness, per-env `SESSION_SECRET` logging everyone out, the liquidsoap boot-line false alarm. |
| 2026-09-18 | Frontend BFF routes & the proxy layer | [memory/frontend_bff.md](memory/frontend_bff.md) | Two failures that looked like app bugs and weren't: a browser fetch with no `app/api/` handler behind it (and the test that now catches the whole class), and an edge proxy hanging up at 60 s and handing back HTML. |
| 2026-09-18 | Auth & access | [memory/auth_access.md](memory/auth_access.md) | Editor invites as a copyable link (no mail stack here): hash-only token storage, single-use enforced in the `WHERE` clause, email-bound so a forwarded link is worthless, and how the token crosses the OAuth round-trip. |
