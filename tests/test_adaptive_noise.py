"""Signal-based tests for trim-to-selection and adaptive noise reduction (issue #66).

These synthesize audio with a known steady tone and an injected short noise
burst, so they exercise the new tool behavior without any database, LLM, or real
catalog file (the server's ``db_manager`` stays None):

- Trim-to-selection keeps only a chosen span, with fades at the cut points.
- ``analyze_and_recommend_processing`` surfaces the detected music span to the
  caller.
- ``reduce_noise`` can sample its noise profile from an explicit clean patch.
- The non-stationary mode removes an intermittent noise burst while degrading the
  underlying tone *less* than the fixed-profile mode at equivalent strength.
- Default (no new arguments) behavior is unchanged.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("librosa")
pytest.importorskip("mcp")
sf = pytest.importorskip("soundfile")

from src.production.big_flavor_mcp import BigFlavorMCPServer

SR = 22050
DURATION = 4.0
TONE_FREQ = 440.0
TONE_AMP = 0.3
BURST = (1.8, 2.4)          # a short broadband noise burst mid-file
BURST_AMP = 0.18
CLEAN = (0.4, 1.5)          # a tone-only span well away from the burst


@pytest.fixture
def server():
    return BigFlavorMCPServer()


def make_tone_with_burst(path: Path) -> np.ndarray:
    """Steady 440 Hz tone across the whole file + a short broadband burst."""
    rng = np.random.default_rng(66)
    n = int(DURATION * SR)
    t = np.arange(n) / SR
    y = TONE_AMP * np.sin(2 * np.pi * TONE_FREQ * t)
    span = (t >= BURST[0]) & (t < BURST[1])
    y[span] += rng.normal(0.0, BURST_AMP, int(span.sum()))
    y = y.astype(np.float32)
    sf.write(str(path), y, SR)
    return y


def tone_amplitude(y: np.ndarray, freq: float, start: float, end: float) -> float:
    """Amplitude of a single frequency within a segment (Goertzel-style)."""
    seg = y[int(start * SR):int(end * SR)]
    t = np.arange(len(seg)) / SR
    return float(np.abs((seg * np.exp(-2j * np.pi * freq * t)).mean()) * 2)


def hf_energy(y: np.ndarray, start: float, end: float) -> float:
    """RMS of content above 1.5 kHz in a segment — captures the broadband burst
    while excluding the 440 Hz tone."""
    from scipy import signal

    seg = y[int(start * SR):int(end * SR)]
    sos = signal.butter(4, 1500, "hp", fs=SR, output="sos")
    hp = signal.sosfilt(sos, seg)
    return float(np.sqrt(np.mean(hp ** 2)))


async def _run(server, tmp_path, **kwargs):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y_in = make_tone_with_burst(in_path)
    result = await server.reduce_noise(
        str(in_path), 1.0, 0.7, str(out_path), **kwargs
    )
    assert result["status"] == "success", result
    y_out, sr_out = sf.read(str(out_path))
    assert sr_out == SR
    return y_in, y_out, result


# --------------------------------------------------------------- adaptive mode

async def test_non_stationary_beats_fixed_profile_on_burst(server, tmp_path):
    pytest.importorskip("noisereduce")

    y_in, y_fixed, _ = await _run(server, tmp_path, non_stationary=False)
    _, y_adaptive, res = await _run(server, tmp_path, non_stationary=True)
    assert res["non_stationary"] is True

    # 1. The adaptive mode actually attacks the intermittent burst.
    burst_in = hf_energy(y_in, *BURST)
    burst_adaptive = hf_energy(y_adaptive, *BURST)
    assert burst_adaptive < burst_in, f"burst {burst_in:.4f} -> {burst_adaptive:.4f}"

    # 2. It removes the burst *better* than the fixed single-profile gate, whose
    #    one profile (sampled from the quietest tone-only frames) isn't matched
    #    to the burst.
    burst_fixed = hf_energy(y_fixed, *BURST)
    assert burst_adaptive < burst_fixed, (
        f"adaptive burst {burst_adaptive:.4f} not below fixed {burst_fixed:.4f}"
    )

    # 3. And it degrades the underlying steady tone *less* than the fixed mode,
    #    which subtracts a tone-shaped profile everywhere.
    tone_fixed = tone_amplitude(y_fixed, TONE_FREQ, *CLEAN)
    tone_adaptive = tone_amplitude(y_adaptive, TONE_FREQ, *CLEAN)
    assert tone_adaptive > tone_fixed, (
        f"adaptive tone {tone_adaptive:.4f} not above fixed {tone_fixed:.4f}"
    )


async def test_explicit_noise_profile_region_is_used(server, tmp_path):
    # Pointing the profile at a clean tone-only patch (0.4-1.5s) rather than the
    # quietest frames still succeeds and returns the region in the result.
    _, _, res = await _run(server, tmp_path, noise_start_s=0.4, noise_end_s=1.4)
    assert res["noise_profile_region"] == {"start_s": 0.4, "end_s": 1.4}
    assert res["status"] == "success"


# ------------------------------------------------------------ trim-to-selection

async def test_trim_to_selection_keeps_only_span(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    make_tone_with_burst(in_path)

    result = await server.trim_silence(
        str(in_path), -40, str(out_path),
        start_s=1.0, end_s=3.0, trim_to_selection=True, fade_ms=20.0
    )
    assert result["status"] == "success", result
    assert result["mode"] == "selection"

    y_out, sr_out = sf.read(str(out_path))
    assert sr_out == SR
    # Duration matches the requested 2.0s span (samples are kept, not blended).
    assert abs(len(y_out) / SR - 2.0) < 0.02, len(y_out) / SR

    # Fades: the very start/end are quieter than the body (smooth cut points).
    head = float(np.sqrt(np.mean(y_out[: int(0.005 * SR)] ** 2)))
    body = float(np.sqrt(np.mean(y_out[int(0.5 * SR): int(1.0 * SR)] ** 2)))
    tail = float(np.sqrt(np.mean(y_out[-int(0.005 * SR):] ** 2)))
    assert head < body and tail < body, (head, body, tail)


async def test_trim_to_selection_requires_a_region(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    make_tone_with_burst(in_path)
    result = await server.trim_silence(
        str(in_path), -40, str(out_path), trim_to_selection=True
    )
    assert result["status"] == "error"
    assert "start_s" in result["error"]


async def test_analyze_surfaces_detected_music_span(server, tmp_path):
    in_path = tmp_path / "in.wav"
    # Leading + trailing silence around a music span, so the detector has a span.
    n = int(DURATION * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    music = (t >= 1.0) & (t < 3.0)
    y[music] = TONE_AMP * np.sin(2 * np.pi * TONE_FREQ * t[music])
    sf.write(str(in_path), y, SR)

    result = await server.analyze_and_recommend_processing(str(in_path))
    assert result["status"] == "success", result
    assert "detected_music_start" in result
    assert "detected_music_end" in result
    assert result["detected_music_start"] == result["recommendations"]["trim"]["detected_music_start"]
    assert result["detected_music_end"] > result["detected_music_start"]


# ------------------------------------------------------------------ regression

async def test_defaults_are_deterministic_and_trim_silence_still_trims(server, tmp_path):
    # reduce_noise with no new args: two runs are identical (no adaptive path).
    _, y1, r1 = await _run(server, tmp_path)
    _, y2, r2 = await _run(server, tmp_path)
    assert r1["non_stationary"] is False
    assert np.array_equal(y1, y2)

    # trim_silence with no new args still removes leading/trailing silence.
    n = int(DURATION * SR)
    t = np.arange(n) / SR
    y = np.zeros(n, dtype=np.float32)
    music = (t >= 1.0) & (t < 3.0)
    y[music] = TONE_AMP * np.sin(2 * np.pi * TONE_FREQ * t[music])
    in_path = tmp_path / "sil.wav"
    out_path = tmp_path / "sil_out.wav"
    sf.write(str(in_path), y, SR)
    result = await server.trim_silence(str(in_path), -40, str(out_path))
    assert result["status"] == "success"
    assert result["mode"] == "silence"
    assert result["trimmed_duration_seconds"] < result["original_duration_seconds"]
