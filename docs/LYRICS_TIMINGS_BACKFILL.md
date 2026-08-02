# Timed Lyrics — Backfill Runbook

How to (re-)generate **timed lyrics** across the catalog, so the player can highlight lyrics in
time with the music.

> **This is the current lyric-extraction path.** The older
> [`LYRICS_QUICKSTART.md`](LYRICS_QUICKSTART.md) / [`LYRICS_EXTRACTION_GUIDE.md`](LYRICS_EXTRACTION_GUIDE.md)
> describe `src/rag/index_lyrics.py`, which predates timed lyrics: it stores lyric *text* only and
> runs on the host. Use this document for anything involving follow-along playback.

---

## What it does, per song

1. **Find isolated vocals.** If the song already has a completed `vocals` stem (from stem
   separation) and the file is still on disk, that file is used directly — no separation needed.
2. **Otherwise separate.** Demucs splits the mix in a temp directory and the vocals are used.
3. **Transcribe.** Whisper `large-v3` runs on the isolated vocals with word timestamps.
4. **Store.** Lyric text goes to `text_embeddings` (unchanged — still the source of truth for lyric
   search); per-line and per-word timings go to the `song_lyric_timings` table.

Vocals matter: Whisper's timestamps drift badly on sung vocals over a full mix. If Demucs is
unavailable or separation fails, the song silently falls back to the mix and is **recorded as such**
so you can spot it afterwards.

---

## Run it

Everything runs inside the backend container — that's where the models and GPU are.

### 1. See where you stand

```bash
docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --status
```

```
Timed-lyric coverage:
  Songs in catalog:      1300
  With current timings:  0
    ...from isolated vocals: 0
    ...from the full mix:    0
  Stale (edited since):  0
  No timings yet:        1300
```

### 2. Sanity-check on a few songs

Always do this before committing to a multi-hour run — it confirms the output looks right and tells
you how long a track actually takes on your hardware.

```bash
docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --limit 3 --yes
```

### 3. The real run

```bash
docker exec bigflavor-backend python -m scripts.backfill_lyric_timings --yes 2>&1 | tee backfill.log
```

> **Drop `-it` when redirecting.** The `-t` flag allocates a TTY, which mangles output written to a
> file. Keep `-it` for interactive steps, drop it when logging.

### 4. Check the result

```bash
docker exec -it bigflavor-backend python -m scripts.backfill_lyric_timings --status
```

Watch the **"from the full mix"** count. Those songs fell back — their timings will be the least
accurate. A handful is normal; a large number means Demucs isn't working and is worth investigating
before you trust the results.

---

## Interrupting and resuming

**It is safe to stop this at any time.** `Ctrl-C` finishes the current song, writes the failure
ledger, and exits. A second `Ctrl-C` abandons the current song immediately.

To resume, **run the exact same command again.** There is no "resume" flag and no state to reset:
a song that has a `song_lyric_timings` row is considered done and is skipped, so the database itself
is the checkpoint.

Failures are recorded in `lyric_timing_backfill_failures.json` (override with `--ledger`). Songs in
that ledger are skipped on later runs so one permanently broken track doesn't get retried forever.

---

## Flags

| Flag | Effect |
|---|---|
| `--status` | Coverage report only. Changes nothing. |
| `--dry-run` | List the songs that would be processed, then exit. |
| `--limit N` | Process at most N songs this run. |
| `--song-id ID` | Process exactly this song. Repeatable. Overrides every other filter. |
| `--redo-all` | Re-extract every song, including ones that already have current timings. |
| `--redo-stale` | Also re-extract songs whose timings went stale after a lyric edit. |
| `--retry-failed` | Ignore the failure ledger and retry previously failed songs. |
| `--no-separate-vocals` | Transcribe the full mix. Faster, noticeably worse timing accuracy. |
| `--yes` / `-y` | Skip the confirmation prompt. |
| `--ledger PATH` | Where to keep the failure ledger. |

### Selection rules worth knowing

- **By default only songs with no timings are processed.** On a first run that *is* the whole
  catalog, so `--redo-all` is unnecessary.
- **`--redo-all` alone is not "everything."** Previously-failed songs are filtered out after
  selection. To genuinely reprocess the entire catalog:

  ```bash
  docker exec bigflavor-backend python -m scripts.backfill_lyric_timings \
    --redo-all --retry-failed --yes 2>&1 | tee backfill.log
  ```

- **Stale timings are left alone by default.** "Stale" means someone hand-edited the lyrics after
  extraction, so the timings no longer match the text. Re-extracting would overwrite those edits
  with a fresh transcription — an explicit choice, hence `--redo-stale`.

---

## Cost

The dominant cost is Demucs, not Whisper. Songs that already have a `vocals` stem skip separation
entirely and are much faster. If most of the catalog has never been stem-separated, expect the long
end of any estimate.

Whisper is loaded **once** for the whole run, not per song — the per-request API path builds one per
call, which across the catalog would be hours of pure model loading.

Separated vocals produced *during* the backfill are written to a temp directory and discarded; they
do not become reusable stem sets. A later `--redo-all` will therefore separate those songs again.

---

## Troubleshooting

**`ERROR: the text embedding model is unavailable`** (exit 2)

You're running outside the container. Storing lyrics re-embeds them, and without
`sentence-transformers` every song would be stored with a zero-vector embedding — which would
silently destroy lyric search across everything the run touched. The script refuses rather than let
that happen. Run it with `docker exec` as shown above.

**`ERROR: could not connect to PostgreSQL`** (exit 2)

The stack isn't up. `docker-compose up -d`.

**Songs failing with "No lyrics detected"**

The transcript came back empty — usually an instrumental, or vocals too buried for Whisper to find.
These land in the ledger and are skipped on resume, which is normally what you want. Inspect the
ledger to see the list.

**Lots of songs recorded as `MIX`**

Demucs isn't loading. Check `docker logs bigflavor-backend` for import errors from `demucs` or
`torch`, and confirm the GPU is visible to the container.

---

## Related

- Design and rationale: [`.agents/ARCHITECTURE.md`](../.agents/ARCHITECTURE.md) → *Search & RAG* →
  Timed lyrics.
- The script: [`scripts/backfill_lyric_timings.py`](../scripts/backfill_lyric_timings.py)
  (`--help` mirrors this table).
- Per-song re-extraction from the UI: `/produce/{songId}` → Audio processing → Lyrics → *Re-extract
  from audio*. It goes through the same code path as this script.
