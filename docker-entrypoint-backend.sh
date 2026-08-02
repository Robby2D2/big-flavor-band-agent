#!/bin/sh
set -e

# Bind-mounted host directories keep whatever ownership the host filesystem
# reports (root, on this project's Docker-Desktop-on-Windows host) — the
# image's build-time `chown -R appuser:appuser /app` only applies to what
# existed in the image itself, and gets shadowed at container start by
# whatever the host mount brings in. Fix ownership of the writable mounts
# here, as root, before dropping to appuser, so a fresh clone / fresh mount
# doesn't repeat the "PermissionError writing playlist" bug.
chown -R appuser:appuser /app/streaming/playlist /app/audio_library/produced 2>/dev/null || true

exec gosu appuser "$@"
