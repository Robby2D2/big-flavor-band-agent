"""
Assert-based tests for the EQ/mastering correctness fixes (issue #59).

These exercise BigFlavorMCPServer's pure audio-processing methods
(apply_eq, apply_mastering, _measure_integrated_lufs) directly against
synthetic sine-wave WAV fixtures — no live DB, no LLM, no MCP transport.
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
DURATION_S = 2.0


def _sine_wav(path: Path, freqs_amps, sr: int = SR, duration: float = DURATION_S):
    t = np.arange(0, duration, 1 / sr)
    y = np.zeros_like(t)
    for freq, amp in freqs_amps:
        y += amp * np.sin(2 * np.pi * freq * t)
    peak = np.max(np.abs(y))
    if peak > 0:
        y = y * (0.5 / peak)
    sf.write(path, y.astype(np.float32), sr)
    return y.astype(np.float32)


def _band_rms_db(y: np.ndarray, sr: int, freq: float, skip: int = None) -> float:
    """RMS magnitude (dB) at the FFT bin nearest ``freq``, over the steady middle of the signal."""
    skip = skip if skip is not None else sr // 2
    y = y[skip:-skip] if len(y) > 2 * skip else y
    spectrum = np.abs(np.fft.rfft(y))
    fft_freqs = np.fft.rfftfreq(len(y), d=1 / sr)
    idx = np.argmin(np.abs(fft_freqs - freq))
    mag = spectrum[idx]
    return 20 * np.log10(mag + 1e-12)


@pytest.fixture
def server():
    return BigFlavorMCPServer(enable_audio_analysis=True)


@pytest.mark.asyncio
async def test_apply_eq_zero_gain_is_identity(server, tmp_path):
    """A neutral EQ pass (no filters requested) leaves the audio unchanged (zero-phase, no gain)."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y_in = _sine_wav(in_path, [(1000.0, 1.0)])

    result = await server.apply_eq(
        str(in_path), 0, None, None, 0, str(out_path), eq_bands=None
    )

    assert result["status"] == "success"
    y_out, sr = sf.read(out_path, dtype="float32")
    assert sr == SR
    # float32 WAV write/read round-trip introduces ~1e-5 quantization noise;
    # a real filtering artifact would be orders of magnitude larger.
    np.testing.assert_allclose(y_out, y_in, atol=1e-4)


@pytest.mark.asyncio
async def test_apply_eq_applies_every_band_not_just_the_last(server, tmp_path):
    """Multiple recommended EQ adjustments (a cut and a boost) must both show up in the output —
    previously only the last "boost"/"reduce" recommendation survived."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    cut_freq, boost_freq = 200.0, 4000.0
    y_in = _sine_wav(in_path, [(cut_freq, 1.0), (boost_freq, 1.0)])

    result = await server.apply_eq(
        str(in_path),
        0,
        None,
        None,
        0,
        str(out_path),
        eq_bands=[
            {"frequency": cut_freq, "gain_db": -6.0},
            {"frequency": boost_freq, "gain_db": 6.0},
        ],
    )

    assert result["status"] == "success"
    assert len(result["eq_bands"]) == 2
    y_out, sr = sf.read(out_path, dtype="float32")

    cut_delta = _band_rms_db(y_out, sr, cut_freq) - _band_rms_db(y_in, sr, cut_freq)
    boost_delta = _band_rms_db(y_out, sr, boost_freq) - _band_rms_db(y_in, sr, boost_freq)

    # Both bands must have moved in the requested direction — if the old bug
    # (only the last adjustment applied) were present, cut_delta would be ~0.
    assert cut_delta < -3.0, f"expected the 200Hz cut to be audible, got {cut_delta:.2f}dB"
    assert boost_delta > 3.0, f"expected the 4kHz boost to be audible, got {boost_delta:.2f}dB"


@pytest.mark.asyncio
@pytest.mark.parametrize("freq,gain_db", [(1000.0, 6.0), (500.0, -6.0), (3000.0, 3.0)])
async def test_apply_eq_peaking_gain_matches_request(server, tmp_path, freq, gain_db):
    """A requested boost/cut of X dB at center frequency f measures within ~1 dB of X at f."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y_in = _sine_wav(in_path, [(freq, 1.0)])

    result = await server.apply_eq(
        str(in_path), 0, None, None, 0, str(out_path),
        eq_bands=[{"frequency": freq, "gain_db": gain_db}],
    )
    assert result["status"] == "success"

    y_out, sr = sf.read(out_path, dtype="float32")
    measured_gain_db = _band_rms_db(y_out, sr, freq) - _band_rms_db(y_in, sr, freq)

    assert abs(measured_gain_db - gain_db) < 1.0, (
        f"requested {gain_db}dB @ {freq}Hz, measured {measured_gain_db:.2f}dB"
    )


def test_measure_integrated_lufs_is_a_real_measurement(server):
    """_measure_integrated_lufs returns a finite BS.1770 figure, not the old rms_db - 15 guess."""
    t = np.arange(0, 3.0, 1 / SR)
    y = (0.5 * np.sin(2 * np.pi * 1000 * t)).astype(np.float64)

    measured = server._measure_integrated_lufs(y, SR)

    assert np.isfinite(measured)
    # A half-scale 1kHz tone should land in a plausible loudness range, not
    # near -70 (silence) or above 0 (impossible for a 0.5 peak signal).
    assert -30.0 < measured < 0.0

    old_guess = 20 * np.log10(np.sqrt(np.mean(y ** 2))) - 15
    assert abs(measured - old_guess) > 0.5, "measurement should differ from the old RMS-based guess"


@pytest.mark.asyncio
async def test_apply_mastering_hits_target_loudness(server, tmp_path):
    """Mastering reports measured before/after LUFS and lands near the target."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    _sine_wav(in_path, [(440.0, 0.1)])  # quiet input, needs gain to reach target

    target = -14.0
    result = await server.apply_mastering(str(in_path), target, str(out_path))

    assert result["status"] == "success"
    assert "input_loudness_lufs" in result
    assert "actual_loudness_lufs" in result
    assert abs(result["actual_loudness_lufs"] - target) < 1.5
