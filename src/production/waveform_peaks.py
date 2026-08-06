"""Waveform drawing envelopes for the produce stem console.

The console draws a waveform per stem, but drawing only ever needs a per-pixel
min/max envelope — a few thousand numbers. Before this module the browser got
that envelope by downloading and decoding the stem's *whole* audio file, and
Demucs writes uncompressed WAV: ~44 MB per stem, ~260 MB for a six-stem set,
every time the tab was opened. This computes the same envelope server-side once
and caches it on the stem row, so the browser fetches ~14 KB of JSON instead.

The envelope is quantised to small ints (``PEAKS_SCALE``) because JSON floats
would triple the payload for precision no canvas can show — a peak is drawn as a
pixel height, and 127 steps is already finer than the ~50 px half-height of the
tallest waveform on screen.

Pure/CPU-bound (a streaming read of a whole file), so callers run it off the
FastAPI event loop via a threadpool. Read-only: nothing here writes audio.
"""
import logging
from typing import Any, Dict

import numpy as np
import soundfile as sf

logger = logging.getLogger("backend-api")

# Bumping this invalidates every cached payload on read (the endpoint only
# serves a cache whose version matches), which is what lets the shape of the
# envelope change without a backfill script.
PEAKS_FORMAT_VERSION = 1

# Buckets per file. The widest consumer is the detail-panel waveform at roughly
# 600-1100 CSS px, so this leaves ~2x headroom; the 144 px stem sparklines are
# pure downsamples of it. The client resamples to its actual canvas width.
PEAKS_RESOLUTION = 2000

# Quantisation range: samples are scaled to [-127, 127] and stored as ints.
PEAKS_SCALE = 127

# Frames per streaming read. Big enough that the per-block numpy overhead is
# irrelevant, small enough that a whole file is never resident — seven of these
# can run concurrently on a box that is also running Demucs.
BLOCK_FRAMES = 1 << 18


def compute_peaks(file_path: str, resolution: int = PEAKS_RESOLUTION) -> Dict[str, Any]:
    """Reduce an audio file to a quantised min/max envelope for drawing.

    Returns the payload cached on the row and sent to the browser verbatim.
    Raises ``ValueError`` for an empty file; ``soundfile`` errors propagate for
    an unreadable one.
    """
    with sf.SoundFile(file_path) as handle:
        frames = handle.frames
        sample_rate = handle.samplerate
        channels = handle.channels
        if frames <= 0:
            raise ValueError(f"Audio file has no frames: {file_path}")

        # A file shorter than the requested resolution gets one bucket per
        # frame rather than empty buckets; the client resamples from whatever
        # width it is given, so a smaller envelope is not a special case there.
        buckets = min(resolution, frames)
        mins = np.full(buckets, np.inf, dtype=np.float32)
        maxs = np.full(buckets, -np.inf, dtype=np.float32)

        offset = 0
        for block in handle.blocks(
            blocksize=BLOCK_FRAMES, dtype="float32", always_2d=True
        ):
            # Mix to mono for the envelope. Note this differs from the old
            # client-side version, which drew channel 0 only — a stem whose
            # channels differ will draw slightly differently than before.
            mono = block.mean(axis=1)
            count = mono.shape[0]
            bucket_of = (
                np.arange(offset, offset + count, dtype=np.int64) * buckets
            ) // frames
            # Bucket indices are monotonic, so each run of equal indices is
            # contiguous and reduceat collapses them in one pass. Only the
            # block seam can land mid-bucket, which the unbuffered min/max
            # accumulate below resolves.
            starts = np.concatenate(([0], np.flatnonzero(np.diff(bucket_of)) + 1))
            np.minimum.at(mins, bucket_of[starts], np.minimum.reduceat(mono, starts))
            np.maximum.at(maxs, bucket_of[starts], np.maximum.reduceat(mono, starts))
            offset += count

    return {
        "version": PEAKS_FORMAT_VERSION,
        "resolution": int(buckets),
        "scale": PEAKS_SCALE,
        "duration_seconds": frames / float(sample_rate),
        "sample_rate": sample_rate,
        "channels": channels,
        "min": _quantise(mins),
        "max": _quantise(maxs),
    }


def _quantise(values: np.ndarray) -> list:
    """Scale float samples to ints in [-PEAKS_SCALE, PEAKS_SCALE].

    Clipping is not just defensive: the produce chain writes float-subtype WAVs
    (see ``audio_io._write_audio``) whose samples can legitimately exceed ±1.0,
    and an unclipped peak would draw outside the canvas.
    """
    # Buckets no block touched keep their ±inf sentinel; a fully silent file is
    # all-inf. nan_to_num flattens both to a zero-height line.
    finite = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    scaled = np.round(finite * PEAKS_SCALE)
    return np.clip(scaled, -PEAKS_SCALE, PEAKS_SCALE).astype(np.int16).tolist()
