#!/usr/bin/liquidsoap

# BigFlavor Radio - Liquidsoap Configuration

# Set up logging - maximum verbosity for debugging
settings.log.file.path := "/var/log/liquidsoap/radio.log"
settings.log.level := 4
settings.log.stdout := true

# Audio settings
settings.frame.audio.samplerate := 44100
settings.frame.audio.channels := 2

# Dynamic playlist from backend
# Reloads every 5 seconds to pick up queue changes
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
def is_catalog_song(r) =
  string.match(pattern="^/audio_library/[0-9]+_[^/]*[.]mp3$", request.uri(r))
end

fallback_music = playlist(
  check_next=is_catalog_song,
  mode="randomize",
  reload=60,
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
            remaining = source.remaining(radio)
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

# Output to Icecast
output.icecast(
  %mp3(bitrate=192),
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
