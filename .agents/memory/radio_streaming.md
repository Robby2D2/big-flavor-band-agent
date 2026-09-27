# Radio Streaming (Icecast + Liquidsoap)

*Reconstructed 2026-06-19 from commit `60da3f0` "Fixed radio" (2025-11-24) and the project CLAUDE.md.*
*Corrected 2026-09-27: the `mksafe()` invariant below described the exact shape that caused issue #104,
and the architecture section still described the in-process radio clock that issue #101 deleted. Both
are rewritten against the code as it now stands — see the #101 and #104 entries in
[MEMORY.md](../MEMORY.md) for how each was measured.*

## Architecture

Live radio is decoupled from the FastAPI request/response cycle:

- **Backend** (`src/api/radio_service.py` + `src/api/routers/radio.py`) keeps radio state — current
  song, queue, play/pause, position — in **PostgreSQL** via `RadioStateStore` (issue #2), not in
  process, so it survives a restart. It writes the playlist file `streaming/playlist/radio.m3u` via
  `write_playlist_file()`.
- **Liquidsoap** (`streaming/radio.liq`) reads that playlist and streams audio to Icecast. It also
  runs a **harbor HTTP listener on container-internal port 8080** serving `GET /on-air` (what is
  actually playing: filename, title, source label, elapsed, remaining) and `POST /skip`.
- **Icecast** broadcasts at `/stream` (proxied by nginx).
- **Shared volume** `./streaming/playlist` is mounted into **both** the backend and liquidsoap
  containers, so the backend writes and Liquidsoap reads the same file.

**The stream is the source of truth for what is playing** (issue #101). The backend no longer runs a
clock of its own: `resolve_on_air_song()` asks `/on-air`, maps the filename back to a song id, and
takes `position` from the stream's `elapsed` each tick. The old simulated clock drifted away from the
audio and, when a song's `duration` was null, pinned Now Playing forever. Skipping goes to the stream
too — `POST /skip` moves the audio rather than only relabelling it.

Radio HTTP surface: `/api/radio/state`, `/api/radio/queue/add`, `/api/radio/queue/remove`,
`/api/radio/skip`, `/api/radio/play`, `/api/radio/pause`, plus `/stream`, `/stream.m3u`,
`/api/audio/stream/{song_id}`. Queue entries carry an `added_by` so a listener can remove their own
add (ACCT-05 / RAD-13); skip and play/pause are editor+.

## Two invariants (regressing either = silent dead air)

1. **Wrap the air chain in `mksafe()` once, around the *result* of the `fallback` — never around each
   child.** `mksafe` is itself an always-ready fallback to silence, so wrapping a child makes that
   child permanently ready and **everything after it unreachable**. That was the #104 defect: with
   `mksafe()` on each child, `fallback_music` was dead code from 2025-11 onwards, and a drained queue
   went to `safe_blank` — then, ~7 seconds later, Icecast logged `Disconnecting source due to socket
   timeout`, `/stream` began returning 404, and Liquidsoap never reconnected. Silence *and* a dead
   mount needing a human.

   ```liquidsoap
   # Correct: children stay fallible so they can yield; mksafe supplies the blank.
   radio = mksafe(fallback(track_sensitive=false, [radio_queue, fallback_music]))
   ```

   `track_sensitive=false` is deliberate: catalog music must yield promptly when a song is queued
   (RAD-08). No `blank()` child — `mksafe` *is* that blank.

2. **Rewrite playlist paths to Liquidsoap's mount points.** The backend writes audio paths as
   `/app/audio_library/song.mp3` but Liquidsoap mounts the library at `/audio_library`, so
   `write_playlist_file()` converts `/app/audio_library` → `/audio_library`. Audio files are matched
   by `{song_id}_*.mp3`.

## The fallback pool is Liquidsoap's own directory scan

`fallback_music` scans `/audio_library` directly, which is what keeps the last line of defence
independent of the backend, HTTP and Postgres. Two consequences:

- The scan is **recursive**, so it reaches `produced/…/stems/…` files whose names carry no song id. A
  `check_next` filter keeps only top-level `{song_id}_*.mp3`.
- A file whose id has **no `songs` row** still plays (74 such files as of 2026-09-27 — issue #107).
  `_song_from_stream()` names those from the stream's own ID3 title, falling back to the filename, so
  the page never claims silence over audible audio (RAD-05). Do **not** "fix" this by filtering the
  pool against the `songs` table: that would put Postgres back in the path of the fallback and cost
  those songs their only route to air.

## Operational gotcha — Liquidsoap config rebuilds

Docker BuildKit aggressively caches the `COPY` layer for `streaming/radio.liq`. A plain
`docker restart` or even `docker-compose build` (without `--no-cache`) will **not** pick up changes —
it will silently keep running the old config, which makes any verification worthless. Force it:
```bash
powershell -Command "(Get-Item 'streaming/radio.liq').LastWriteTime = Get-Date"
docker stop bigflavor-liquidsoap && docker rm bigflavor-liquidsoap
docker-compose build --no-cache liquidsoap
docker-compose up -d liquidsoap
```
Confirm what is actually running before trusting a measurement:
```bash
docker exec bigflavor-liquidsoap md5sum /etc/liquidsoap/radio.liq   # compare to the committed file
```

Debug with `docker logs bigflavor-liquidsoap --tail 100`, or ask the stream directly:
`docker exec bigflavor-backend curl -s http://liquidsoap:8080/on-air`. If it is streaming
`safe_blank` instead of the playlist, suspect the air-chain shape (invariant 1) or a path-rewrite
mismatch (invariant 2).

**`reload_mode="watch"` does not fire on the Docker Desktop/Windows bind mount** — it needs inotify,
so on Windows the queue playlist only reloads at container start. Force one over telnet when testing:
`docker exec bigflavor-liquidsoap bash -c 'echo "radio.m3u.reload" | telnet localhost 1234'`.
