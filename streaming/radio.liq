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

# Fallback to random songs from library if playlist is empty
fallback_music = playlist(
  mode="randomize",
  reload=60,
  "/audio_library"
)

# Tag which source a track came from, so the backend can say whether what is on the
# air is something a listener queued or music the stream picked itself (issue #101).
# Tagged before mksafe, so only real tracks carry the tag.
radio_queue = metadata.map(
  insert_missing=true,
  fun (_) -> [("bigflavor_source", "queue")],
  radio_queue
)
fallback_music = metadata.map(
  insert_missing=true,
  fun (_) -> [("bigflavor_source", "fallback")],
  fallback_music
)

# Use queue first, fallback to random if empty
# mksafe ensures sources don't fail and always provide audio
radio_queue = mksafe(radio_queue)
fallback_music = mksafe(fallback_music)
radio = fallback([radio_queue, fallback_music, blank()])

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
