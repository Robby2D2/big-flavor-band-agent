# Catalog Scraping & Ingest

*Reconstructed 2026-06-19 from commits across 2025-11-06 → 2025-11-10 (`c52897d` screen scraping;
`70f20fc` de-duplication; `dfe659c` scraped all songs; `eb66637` index audio too; `0088ee6` index
all bigflavor songs; `3380d15` process only missing data; `c87a6e4` scraping fixes).*

## What it does

The `scraper/` directory ingests the Big Flavor Band catalog (from bigflavor.com) into PostgreSQL —
song metadata, lyrics, and audio embeddings — so everything is searchable by the RAG system.

Scripts: `scraper/process_all_songs.py`, `process_new_songs.py`, `process_existing_songs.py`,
`add_audio_analysis.py`, `inspect_html.py` (plus assorted `tests/` runners like
`test_incremental_scrape.py`).

## Key properties

- **De-duplicated** — scraping was fixed to avoid duplicate song rows (`70f20fc`).
- **Audio + metadata** — ingest indexes audio embeddings as well as metadata (`eb66637`), so
  audio-similarity search works across the whole catalog.
- **Incremental** — re-runs can **process only missing data** (`3380d15`) rather than re-scraping
  everything. Prefer this incremental path for routine top-ups; full re-index only when specifically
  needed.

## Where the data lands

PostgreSQL + pgvector via `DatabaseManager`. Schema bootstrapped from `database/sql/init/*.sql`
(songs → details → audio embeddings); `song_id` is an integer (migration `04`). Audio files on disk
are matched to songs by the `{song_id}_*.mp3` naming convention (the radio playlist writer relies on
this too).

## Operational note

Keep indexes in sync with the songs: if a song's metadata/lyrics change (editing was added in
`a26b484`/`ce6d272`), its lyric/text/audio indexes must be regenerated or search will return stale
results (OKR O4.2).
