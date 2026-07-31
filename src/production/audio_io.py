"""Shared audio I/O helpers used by every production tool.

Channel-count-preserving load/write plus the per-channel apply helper, and the
WAV subtype constants that keep the auto-clean chain float end-to-end. Moved out
of ``big_flavor_mcp`` (issue: per-tool refactor) so the tool modules can share
them without importing the server. ``big_flavor_mcp`` re-exports these names for
backward compatibility.
"""

from typing import Optional

# Import librosa for audio analysis (optional at import time).
try:
    import librosa  # noqa: F401
    import numpy as np  # noqa: F401
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False


# Auto-clean chain precision (issue #58): the processing is float end-to-end,
# so intermediate step files are written as 32-bit float WAV — re-quantizing to
# soundfile's 16-bit default between steps adds noise at the very floor the
# chain is cleaning. Only the final output is quantized, once, to 24-bit PCM
# (the deliberate master bit depth).
INTERMEDIATE_WAV_SUBTYPE = "FLOAT"
FINAL_WAV_SUBTYPE = "PCM_24"


def _load_audio(file_path: str, sr: Optional[int] = None) -> tuple:
    """Load audio preserving the input's channel count.

    Returns (y, sample_rate) where y is 1-D for mono input or
    (channels, samples) for multi-channel input (librosa layout).
    """
    import librosa

    return librosa.load(file_path, sr=sr, mono=False)


def _to_mono(y):
    """Mono reference mix for analysis (beat/pitch/RMS detection)."""
    import librosa

    return librosa.to_mono(y) if y.ndim > 1 else y


def _apply_per_channel(y, process):
    """Apply a 1-D signal-processing function to each channel.

    Mono passes straight through. Multi-channel results are trimmed to the
    shortest channel because STFT round-trips can differ by a few samples.
    """
    import numpy as np

    if y.ndim == 1:
        return process(y)
    processed = [process(channel) for channel in y]
    min_len = min(p.shape[-1] for p in processed)
    return np.vstack([p[..., :min_len] for p in processed])


def _write_audio(output_path: str, y, sr: int, subtype: Optional[str] = None) -> None:
    """Write audio, converting librosa's (channels, samples) layout to
    soundfile's (samples, channels). `subtype` defaults to soundfile's own
    default (PCM_16) when not given; pass INTERMEDIATE_WAV_SUBTYPE /
    FINAL_WAV_SUBTYPE explicitly where precision matters (issue #58)."""
    import soundfile as sf

    sf.write(output_path, y.T if y.ndim > 1 else y, sr, subtype=subtype)
