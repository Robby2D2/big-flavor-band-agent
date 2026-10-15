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

---

## Later entries

*The entries below moved here from [MEMORY.md](../MEMORY.md) in the 2026-10-15 prune.*

### 2026-09-27 — 74 playable songs were not in the catalog, and indexing had silently stopped (issue #107)
`audio_library/` held 1,415 top-level `{song_id}_*.mp3` files against 1,341 `songs` rows. The 74
without a row were playable but undiscoverable: search, the DJ, lyrics and embeddings all start from
the catalog, so the radio's own directory scan was the only way they could reach a listener (**CAT-01**
— a song that cannot be surfaced by any search mode is a defect). Found while fixing #104, which only
made them audible.

**Cause, from the cached scrapes rather than a guess.** `scraper/scraped_songs_20251106_173012.json`
still describes 60 of the 74; the 2025-11-10 scrape the catalog was loaded from describes **none** of
them. They were dropped between the two scrapes and their files stayed behind. So the back-fill
(`scripts/backfill_orphan_songs.py`) prefers that older scrape — keyed by slug, numeric id inside
`audio_url` — then the file's own ID3 title via ffprobe (14 songs), then the filename (0 needed).

**The real find was that indexing was dead.** The first back-fill run filled *nothing*: 74 failures,
all "no usable features". `librosa.beat.beat_track` returns tempo as a 1-element array and numpy 2.5
refuses `float()` on one; a blanket `except` around the whole feature block turned that into an empty
dict. **Every song indexed since the librosa 1.0 / numpy 2.5 upgrade had lost its tempo, key and
duration** — invisible because the 1,341 rows indexed before it still had theirs. `as_scalar()` fixes
it; the lesson is the blanket `except`, which made a type error indistinguishable from "this song has
no tempo".

**Delivered:** 74 rows inserted; duration + tempo now 1,415/1,415; metadata embeddings 1,415/1,415, so
the songs are findable (spot-checked: 2343, 2538 rank first for their titles, 890 first for its own);
audio embeddings 1,415/1,415.

**Left undone, deliberately:** those 74 still have no lyrics (Whisper hours) and therefore no genre,
which `derive_genre` infers *from* lyrics — so they rank on title alone; 1063 "So Tired" sits 19th
among ~18 same-titled songs. Also found: **`clap_embedding` is NULL for all 1,415 rows going back to
2025-11-09** — CLAP has never worked here (`clap_processor(audios=…)` is the kwarg transformers
renamed), so every `combined_embedding` is the librosa fallback. Left alone on purpose: fixing the
kwarg now would give 74 songs CLAP vectors while 1,341 keep fallback ones, which is a worse state than
uniformly-degraded (**CAT-05**). It needs its own issue and a full re-index.

**Also:** `scraper/` is now mounted read-only into the backend container beside `scripts/`, because the
back-fill reuses the scraper's own `insert_song_with_details` and reads those cached scrapes.
