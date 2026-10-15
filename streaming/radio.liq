#!/usr/bin/liquidsoap

# BigFlavor Radio - Liquidsoap Configuration

# Set up logging - maximum verbosity for debugging
settings.log.file.path := "/var/log/liquidsoap/radio.log"
settings.log.level := 4
settings.log.stdout := true

# Audio settings
settings.frame.audio.samplerate := 44100
settings.frame.audio.channels := 2

# Dynamic playlist from backend, reloaded when the backend rewrites it.
# reload=5 is inert here: reload_mode="watch" reloads on a file change, not on a
# timer, so the number is not a 5-second poll -- do not read it as one.
# Use "randomize" mode with a single item to ensure source stays ready
radio_queue = playlist(
  mode="randomize",
  reload=5,
  reload_mode="watch",
  "/playlist/radio.m3u"
)

# Fallback to random songs from library if playlist is empty.
# Restricted to the catalog's own "{song_id}_*.mp3" files, because the directory scan
# is recursive and /audio_library also holds produced/ (isolated Demucs stems, .opus
# previews) and sessions/ (rehearsal takes) -- 2255 files against 1415 catalog songs.
# Measured on the live stack, it queued produced/.../previews/guitar.opus: a lone
# guitar stem is not what the station is for, and its filename carries no song id, so
# the radio page could not name what a listener was hearing (RAD-05).
# The shape is all this can check: 74 of these files have no catalog row, and naming
# those is the backend's job (_song_from_stream in src/api/radio_service.py), not a
# reason to keep playable songs off the air.
def is_catalog_song(r) =
  string.match(pattern="^/audio_library/[0-9]+_[^/]*[.]mp3$", request.uri(r))
end

# Rescanned once a day. A rescan walks every file under /audio_library -- ~1.3 s
# for 2366 files on the Docker Desktop bind mount, measured 2026-10-15 -- and it
# used to run every 60 s, paused or not, finding nothing: no app path adds a
# top-level "{song_id}_*.mp3" (produced session songs live under produced/, which
# is_catalog_song skips), and the newest one dates from 2025-11-10. A file copied in
# by hand is picked up by the next daily scan, or at once by restarting this
# container; queueing it never waited on this, the queue is its own playlist.
fallback_music = playlist(
  check_next=is_catalog_song,
  mode="randomize",
  reload=86400,
  "/audio_library"
)

# Tag which source a track came from, so the backend can say whether what is on the
# air is something a listener queued or music the stream picked itself (issue #101).
# Tagged before mksafe, so only real tracks carry the tag.
# The ids also name these sources in the log's own "Switch to ..." lines, which is
# how the air chain's decisions are read back (PLAT-10).
radio_queue = metadata.map(
  id="radio_queue",
  insert_missing=true,
  fun (_) -> [("bigflavor_source", "queue")],
  radio_queue
)
fallback_music = metadata.map(
  id="catalog_fallback",
  insert_missing=true,
  fun (_) -> [("bigflavor_source", "fallback")],
  fallback_music
)

# Use the queue first and catalog music whenever the queue has nothing to play.
#
# The children stay fallible on purpose and mksafe wraps the *result*. mksafe makes a
# source always ready -- that is its whole job -- so an mksafe'd child can never yield
# to the next one: wrapping them individually is what made fallback_music unreachable
# and sent a drained queue to dead air, and then to a dropped Icecast mount (issue
# #104, RAD-02). The always-ready guarantee AGENTS.md requires is unchanged, only
# applied once at the top, so the output still cannot fail and a cold start where
# neither playlist has resolved a file yet picks audio up on its own. No blank() child
# either: mksafe *is* that blank, and a blank() in the list would be a second
# always-ready source with the same effect.
#
# track_sensitive=false so a song added to an empty queue takes the air in seconds
# instead of waiting out the catalog track that is playing (RAD-08).
radio = mksafe(fallback(track_sensitive=false, [radio_queue, fallback_music]))

# Apply some processing
radio = normalize(radio)

# --- What is actually on the air ------------------------------------------
# The backend used to name the current song from a clock of its own, which drifted
# away from real playback (issue #101). It asks the stream instead: the metadata of
# every track that starts on air is remembered here and served as JSON over harbor,
# so whatever is playing -- a queued song or fallback music -- is reported by the
# file that is playing it. The port is container-internal (docker network only);
# the backend reaches it at http://liquidsoap:8080.
on_air = ref([])
radio = source.on_track(radio, fun (m) -> on_air := m)

# Output to Icecast. Named so an editor's pause can stop it outright (RAD-07): a
# stopped output stops pulling audio, so nothing is decoded or encoded and the
# /stream mount goes away until it is started again. That is the only way a pause
# saves anything -- relabelling a stream that keeps encoding does not.
# fallible=true is only what lets Liquidsoap 2.2 stop an output at all ("Source is
# infallible and cannot be stopped"); the air chain under it is still mksafe'd.
air = output.icecast(
  %mp3(bitrate=192),
  fallible=true,
  host="icecast",
  port=8000,
  password="bigflavor_source",
  mount="/stream",
  name="BigFlavor Radio",
  description="Original music from Big Flavor",
  genre="Various",
  url="https://bigflavor.useunix.com",
  radio
)

# Interactive controls via telnet
settings.server.telnet := true
settings.server.telnet.bind_addr := "0.0.0.0"
settings.server.telnet.port := 1234

# Log startup
log("BigFlavor Radio started!")

harbor.http.register.simple(
  port=8080,
  method="GET",
  "/on-air",
  fun (_) ->
    begin
      m = on_air()
      http.response(
        content_type="application/json",
        data=json.stringify(
          compact=true,
          {
            filename = m["filename"],
            title = m["title"],
            source = m["bigflavor_source"],
            elapsed = source.elapsed(radio),
            remaining = source.remaining(radio),
            running = air.is_started()
          }
        )
      )
    end
)

# Skipping has to move the audio, not just the label the backend shows.
harbor.http.register.simple(
  port=8080,
  method="POST",
  "/skip",
  fun (_) ->
    begin
      source.skip(radio)
      http.response(content_type="application/json", data='{"skipped":true}')
    end
)

# Pause and resume the broadcast itself. The backend holds which one is wanted and
# re-applies it every tick, so a pause survives this container restarting (RAD-04)
# -- a fresh start comes up broadcasting and is stopped again within a second.
harbor.http.register.simple(
  port=8080,
  method="POST",
  "/stop",
  fun (_) ->
    begin
      air.stop()
      http.response(content_type="application/json", data='{"running":false}')
    end
)

harbor.http.register.simple(
  port=8080,
  method="POST",
  "/start",
  fun (_) ->
    begin
      air.start()
      http.response(content_type="application/json", data='{"running":true}')
    end
)
