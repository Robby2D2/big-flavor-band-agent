# Radio Streaming (Icecast + Liquidsoap)

*Reconstructed 2026-06-19 from commit `60da3f0` "Fixed radio" (2025-11-24) and the project CLAUDE.md.*

## Architecture

Live radio is decoupled from the FastAPI request/response cycle:

- **Backend** (`backend_api.py`) holds `radio_state` (current song, queue, play/pause, position) in
  process and writes the playlist file `streaming/playlist/radio.m3u` via `write_playlist_file()`.
- **Liquidsoap** (`streaming/radio.liq`) reads that playlist and streams audio to Icecast.
- **Icecast** broadcasts at `/stream` (proxied by nginx).
- **Shared volume** `./streaming/playlist` is mounted into **both** the backend and liquidsoap
  containers, so the backend writes and Liquidsoap reads the same file.

Radio HTTP surface: `/api/radio/state`, `/api/radio/queue/add`, `/api/radio/queue/remove`,
`/api/radio/skip`, `/api/radio/play`, `/api/radio/pause`, plus `/stream`, `/stream.m3u`,
`/api/audio/stream/{song_id}`.

## Two invariants (regressing either = silent dead air)

1. **Wrap Liquidsoap playlist sources in `mksafe()`.** Otherwise the `fallback` operator selects
   `blank()` (silence) even when the playlist files exist and are valid, because playlist sources can
   look "not ready" during initialization:
   ```liquidsoap
   radio_queue = mksafe(radio_queue)
   fallback_music = mksafe(fallback_music)
   radio = fallback([radio_queue, fallback_music, blank()])
   ```

2. **Rewrite playlist paths to Liquidsoap's mount points.** The backend writes audio paths as
   `/app/audio_library/song.mp3` but Liquidsoap mounts the library at `/audio_library`, so
   `write_playlist_file()` converts `/app/audio_library` → `/audio_library`. Audio files are matched
   by `{song_id}_*.mp3`.

## Operational gotcha — Liquidsoap config rebuilds

Docker BuildKit aggressively caches the `COPY` layer for `streaming/radio.liq`. A plain
`docker restart` or even `docker-compose build` (without `--no-cache`) will **not** pick up changes.
Force it:
```bash
powershell -Command "(Get-Item 'streaming/radio.liq').LastWriteTime = Get-Date"
docker stop bigflavor-liquidsoap && docker rm bigflavor-liquidsoap
docker-compose build --no-cache liquidsoap
docker-compose up -d liquidsoap
```

Debug with `docker logs bigflavor-liquidsoap --tail 100` — if it's streaming `blank()` instead of the
playlist, suspect a missing `mksafe()` or a path-rewrite mismatch.
