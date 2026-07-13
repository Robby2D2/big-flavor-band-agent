"""
Assert-based tests for reduce_noise (issue #56).

These synthesize audio with known music segments and a noise-only gap, so they
exercise the noise-profile estimation, gate smoothing, and high-pass option
without any database, LLM, or real catalog file. The key regression: the input
file *starts with music* (as it does after auto-clean's trim step), so a
"sample the first second" noise profile would subtract musical content.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.production.big_flavor_mcp import BigFlavorMCPServer

SR = 22050
DURATION = 4.0
NOISE_AMP = 0.01
TONE_AMP = 0.35
# Music plays 0-1.5s and 2.5-4s; 1.5-2.5s is the noise-only gap.
MUSIC_SPANS = [(0.0, 1.5), (2.5, DURATION)]
GAP = (1.5, 2.5)


def make_signal(tone_freqs, path: Path) -> np.ndarray:
    rng = np.random.default_rng(56)
    n = int(DURATION * SR)
    t = np.arange(n) / SR
    y = rng.normal(0.0, NOISE_AMP, n)
    for start, end in MUSIC_SPANS:
        span = (t >= start) & (t < end)
        for freq in tone_freqs:
            y[span] += TONE_AMP * np.sin(2 * np.pi * freq * t[span])
    y = y.astype(np.float32)
    sf.write(str(path), y, SR)
    return y


def segment_rms(y: np.ndarray, start: float, end: float) -> float:
    seg = y[int(start * SR):int(end * SR)]
    return float(np.sqrt((seg ** 2).mean()))


def tone_amplitude(y: np.ndarray, freq: float, start: float, end: float) -> float:
    """Amplitude of a single frequency within a segment (Goertzel-style)."""
    seg = y[int(start * SR):int(end * SR)]
    t = np.arange(len(seg)) / SR
    return float(np.abs((seg * np.exp(-2j * np.pi * freq * t)).mean()) * 2)


@pytest.fixture
def server():
    return BigFlavorMCPServer()


async def run_reduce_noise(server, tmp_path, tone_freqs, **kwargs):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y_in = make_signal(tone_freqs, in_path)
    result = await server.reduce_noise(
        str(in_path), 1.0, 0.7, str(out_path), **kwargs
    )
    assert result["status"] == "success", result
    y_out, sr_out = sf.read(str(out_path))
    assert sr_out == SR
    assert len(y_out) == len(y_in)
    return y_in, y_out, result


async def test_noise_drops_and_music_survives_when_file_starts_with_music(server, tmp_path):
    y_in, y_out, result = await run_reduce_noise(server, tmp_path, (440.0, 3520.0))

    # The noise-only gap gets quieter...
    gap_in = segment_rms(y_in, GAP[0] + 0.1, GAP[1] - 0.1)
    gap_out = segment_rms(y_out, GAP[0] + 0.1, GAP[1] - 0.1)
    assert gap_out < 0.5 * gap_in, f"noise floor {gap_in:.4f} -> {gap_out:.4f}"
    assert result["noise_reduction_db"] > 0

    # ...while music (including high-frequency content) is preserved, even
    # though the file starts with music — a first-N-seconds noise profile
    # would have gated it away.
    for freq in (440.0, 3520.0):
        amp_in = tone_amplitude(y_in, freq, 0.2, 1.3)
        amp_out = tone_amplitude(y_out, freq, 0.2, 1.3)
        assert amp_out >= 0.7 * amp_in, f"{freq} Hz {amp_in:.4f} -> {amp_out:.4f}"


async def test_sub_60hz_content_passes_by_default(server, tmp_path):
    y_in, y_out, result = await run_reduce_noise(server, tmp_path, (40.0,))
    assert result["highpass_hz"] is None
    amp_in = tone_amplitude(y_in, 40.0, 0.2, 1.3)
    amp_out = tone_amplitude(y_out, 40.0, 0.2, 1.3)
    assert amp_out >= 0.7 * amp_in, f"40 Hz {amp_in:.4f} -> {amp_out:.4f}"


async def test_highpass_attenuates_low_end_only_when_enabled(server, tmp_path):
    y_in, y_out, result = await run_reduce_noise(
        server, tmp_path, (40.0,), highpass_hz=60.0
    )
    assert result["highpass_hz"] == 60.0
    amp_in = tone_amplitude(y_in, 40.0, 0.2, 1.3)
    amp_out = tone_amplitude(y_out, 40.0, 0.2, 1.3)
    assert amp_out < 0.4 * amp_in, f"40 Hz {amp_in:.4f} -> {amp_out:.4f}"
