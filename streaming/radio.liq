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

# Use queue first, fallback to random if empty
# mksafe ensures sources don't fail and always provide audio
radio_queue = mksafe(radio_queue)
fallback_music = mksafe(fallback_music)
radio = fallback([radio_queue, fallback_music, blank()])

# Apply some processing
radio = normalize(radio)

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
