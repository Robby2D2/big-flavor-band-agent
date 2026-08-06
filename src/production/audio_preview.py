"""Compressed playback copies of stem/version audio for the produce console.

Demucs writes uncompressed WAV — ~44 MB per stem — and the console needs every
stem decoded at once to play them in sync. Sending the WAVs meant ~260 MB per
tab open for audio the browser immediately re-encodes into memory anyway. These
are lossy copies made purely so the *browser* can play a stem; every DSP tool,
every fix, and the A/B fidelity comparison still read the original file.

Two rules make this cache safe without any invalidation logic:

1. **The preview path is derived from the source file's path, never a row id.**
   Produce never overwrites audio in place — a re-clean writes a new timestamped
   file, a re-separation writes a new stem-set directory — so a preview can only
   ever describe the file it was named after.
2. **Nothing is written outside ``produced/``.** The catalog mount is read-only
   (``./audio_library:/app/audio_library:ro``), which is why version previews
   live in a shared directory rather than beside their source.

Transcoding shells out to ffmpeg (a system package in the backend image) and is
blocking, so callers run it off the event loop.
"""
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("backend-api")

# Opus in an Ogg container: the best size/quality trade at this bitrate, and
# decodable by Chrome, Firefox, Edge and Safari 17.4+. Swapping the whole codec
# is deliberately these four constants (AAC in MP4 would be the universal but
# larger alternative) — there is no negotiation or fallback ladder.
PREVIEW_CODEC = "libopus"
PREVIEW_SUFFIX = ".opus"
PREVIEW_MEDIA_TYPE = "audio/ogg"
PREVIEW_BITRATE = "96k"
# Passed to ffmpeg as -f. Stated explicitly because the encode writes to a
# ".part" temp file, and ffmpeg otherwise picks the muxer from the output
# filename's extension — which would be ".part" and fails outright.
PREVIEW_FORMAT = "ogg"

PREVIEW_SUBDIR = "previews"
PREVIEW_TIMEOUT_S = 300

# Re-encoding an already-lossy file would cost a generation of quality to save
# little: the catalog originals are ~4 MB MP3s, against ~44 MB stem WAVs.
ALREADY_COMPRESSED = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".webm"}


def stem_preview_path(stem_path: Path) -> Path:
    """Where a stem's playback copy lives: a previews/ dir beside the stem.

    Stems already sit in a per-set directory under produced/, so this inherits
    the set's lifetime — a re-separation makes a new set directory, and a failed
    job's cleanup removes the previews with it.
    """
    return stem_path.parent / PREVIEW_SUBDIR / f"{stem_path.stem}{PREVIEW_SUFFIX}"


def version_preview_path(version_audio_path: Path, produced_dir: Path) -> Path:
    """Where a version's playback copy lives: a shared previews/ dir.

    Unlike stems, a version's audio can be a catalog original on the read-only
    mount, so the preview cannot go beside it. Names stay unique because catalog
    and produced filenames are both song-id prefixed and flat.
    """
    return produced_dir / PREVIEW_SUBDIR / f"{version_audio_path.stem}{PREVIEW_SUFFIX}"


def build_preview(source_path: str, output_path: str) -> str:
    """Transcode ``source_path`` to a compressed playback copy. Returns the path to serve.

    Already-compressed sources are passed straight through — the returned path
    is then the source itself, not ``output_path``. Blocking (subprocess), so
    callers run it off the event loop.

    Raises ``FileNotFoundError`` if ffmpeg is not installed and
    ``subprocess.CalledProcessError`` if the encode fails.
    """
    source = Path(source_path)
    if source.suffix.lower() in ALREADY_COMPRESSED:
        return str(source)

    output = Path(output_path)
    if output.exists():
        return str(output)

    output.parent.mkdir(parents=True, exist_ok=True)
    # Encode to a temp name in the same directory and rename on success, so a
    # crashed or concurrent encode can never leave a truncated file that later
    # looks like a valid cache hit.
    partial = output.with_name(f"{output.name}.part")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",  # never let ffmpeg consume the server's stdin
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(source),
                "-vn",
                "-map_metadata", "-1",
                "-c:a", PREVIEW_CODEC,
                "-b:a", PREVIEW_BITRATE,
                "-vbr", "on",
                "-ac", "2",
                "-ar", "48000",  # Opus's native rate; resampling here is unavoidable
                "-f", PREVIEW_FORMAT,
                str(partial),
            ],
            check=True,
            capture_output=True,
            timeout=PREVIEW_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as exc:
        # ffmpeg puts the actual reason on stderr; without this the failure is
        # just "returned 1".
        logger.error(
            "ffmpeg failed for %s: %s", source, exc.stderr.decode(errors="replace")
        )
        partial.unlink(missing_ok=True)
        raise
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    os.replace(partial, output)
    return str(output)
