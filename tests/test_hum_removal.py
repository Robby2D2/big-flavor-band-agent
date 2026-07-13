"""
Assert-based tests for mains-hum detection and removal (issue #57).

These synthesize audio with known musical tones, optionally polluted by a
50 or 60 Hz mains hum plus harmonics, so they exercise detection (including
picking the correct fundamental), notch-filter removal, and the auto-clean
integration without any database, LLM, or real catalog file.
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
NOISE_AMP = 0.005
MUSIC_TONES = (82.0, 440.0)  # low E + A4: content adjacent to, but not at, mains frequencies
MUSIC_AMP = 0.3
HUM_AMP = 0.05


def make_signal(path: Path, hum_freqs=()) -> np.ndarray:
    """Full-length music tones + faint broadband noise, plus optional hum."""
    rng = np.random.default_rng(57)
    n = int(DURATION * SR)
    t = np.arange(n) / SR
    y = rng.normal(0.0, NOISE_AMP, n)
    for freq in MUSIC_TONES:
        y += MUSIC_AMP * np.sin(2 * np.pi * freq * t)
    for freq in hum_freqs:
        y += HUM_AMP * np.sin(2 * np.pi * freq * t)
    y = (y / np.max(np.abs(y)) * 0.8).astype(np.float32)
    sf.write(str(path), y, SR)
    return y


def tone_amplitude(y: np.ndarray, freq: float) -> float:
    """Amplitude of a single frequency component (Goertzel-style)."""
    t = np.arange(len(y)) / SR
    return float(np.abs((y * np.exp(-2j * np.pi * freq * t)).mean()) * 2)


@pytest.fixture
def server():
    return BigFlavorMCPServer()


# ---------------------------------------------------------------- detection

async def test_analysis_reports_60hz_hum_with_harmonics(server, tmp_path):
    in_path = tmp_path / "hum60.wav"
    make_signal(in_path, hum_freqs=(60.0, 120.0, 180.0))

    analysis = await server.analyze_and_recommend_processing(str(in_path))
    assert analysis["status"] == "success", analysis

    hum = analysis["recommendations"]["hum"]
    assert hum["recommended"] is True
    assert hum["fundamental_hz"] == 60.0
    for freq in (60.0, 120.0, 180.0):
        assert freq in hum["harmonics_affected"], hum
    assert "Mains hum at 60 Hz" in analysis["summary"]


async def test_analysis_reports_50hz_hum_not_60(server, tmp_path):
    in_path = tmp_path / "hum50.wav"
    make_signal(in_path, hum_freqs=(50.0, 100.0, 150.0))

    analysis = await server.analyze_and_recommend_processing(str(in_path))
    assert analysis["status"] == "success", analysis

    hum = analysis["recommendations"]["hum"]
    assert hum["recommended"] is True
    assert hum["fundamental_hz"] == 50.0


async def test_analysis_reports_no_hum_on_clean_audio(server, tmp_path):
    in_path = tmp_path / "clean.wav"
    make_signal(in_path)

    analysis = await server.analyze_and_recommend_processing(str(in_path))
    assert analysis["status"] == "success", analysis

    hum = analysis["recommendations"]["hum"]
    assert hum["recommended"] is False
    assert hum["fundamental_hz"] is None
    assert hum["harmonics_affected"] == []
    assert "Mains hum" not in analysis["summary"]


# ------------------------------------------------------------------ removal

async def test_remove_hum_notches_hum_and_preserves_music(server, tmp_path):
    in_path = tmp_path / "hum60.wav"
    out_path = tmp_path / "dehummed.wav"
    y_in = make_signal(in_path, hum_freqs=(60.0, 120.0, 180.0))

    result = await server.remove_hum(str(in_path), str(out_path))
    assert result["status"] == "success", result
    assert result["hum_detected"] is True
    assert result["fundamental_hz"] == 60.0
    for freq in (60.0, 120.0, 180.0):
        assert freq in result["harmonics_notched"], result

    y_out, sr_out = sf.read(str(out_path))
    assert sr_out == SR
    assert len(y_out) == len(y_in)

    # Hum frequencies are strongly attenuated...
    for freq in (60.0, 120.0, 180.0):
        amp_in = tone_amplitude(y_in, freq)
        amp_out = tone_amplitude(y_out, freq)
        assert amp_out < 0.2 * amp_in, f"{freq} Hz {amp_in:.4f} -> {amp_out:.4f}"

    # ...while adjacent musical content is not audibly dented (82 Hz sits
    # between the 60 and 120 Hz notches; 440 Hz is far above them).
    for freq in MUSIC_TONES:
        amp_in = tone_amplitude(y_in, freq)
        amp_out = tone_amplitude(y_out, freq)
        assert amp_out >= 0.85 * amp_in, f"{freq} Hz {amp_in:.4f} -> {amp_out:.4f}"


async def test_remove_hum_on_clean_audio_copies_unchanged(server, tmp_path):
    in_path = tmp_path / "clean.wav"
    out_path = tmp_path / "out.wav"
    make_signal(in_path)

    result = await server.remove_hum(str(in_path), str(out_path))
    assert result["status"] == "success", result
    assert result["hum_detected"] is False

    # No filtering applied: the output is a byte-for-byte copy of the input.
    assert out_path.read_bytes() == in_path.read_bytes()


async def test_remove_hum_with_forced_fundamental(server, tmp_path):
    in_path = tmp_path / "hum50.wav"
    out_path = tmp_path / "out.wav"
    y_in = make_signal(in_path, hum_freqs=(50.0, 100.0))

    result = await server.remove_hum(str(in_path), str(out_path), fundamental_hz=50)
    assert result["status"] == "success", result
    assert result["fundamental_hz"] == 50.0

    y_out, _ = sf.read(str(out_path))
    for freq in (50.0, 100.0):
        amp_in = tone_amplitude(y_in, freq)
        amp_out = tone_amplitude(y_out, freq)
        assert amp_out < 0.2 * amp_in, f"{freq} Hz {amp_in:.4f} -> {amp_out:.4f}"


# --------------------------------------------------------------- auto-clean

# Isolate the hum step: every other stage off, hum follows the analysis.
OTHER_STEPS_OFF = {
    "trim": False,
    "noise_reduction": False,
    "eq": False,
    "normalize": False,
    "master": False,
}


async def test_auto_clean_applies_and_reports_hum_removal(server, tmp_path):
    in_path = tmp_path / "hum60.wav"
    out_path = tmp_path / "cleaned.wav"
    y_in = make_signal(in_path, hum_freqs=(60.0, 120.0))

    result = await server.auto_clean_recording(
        str(in_path), str(out_path), steps_override=OTHER_STEPS_OFF
    )
    assert result["status"] == "success", result

    hum_steps = [s for s in result["steps_applied"] if s["step"] == "hum_removal"]
    assert len(hum_steps) == 1, result["steps_applied"]
    assert hum_steps[0]["fundamental_hz"] == 60.0
    assert result["recommendations_followed"]["hum_removal"] is True

    y_out, _ = sf.read(str(out_path))
    amp_in = tone_amplitude(y_in, 60.0)
    amp_out = tone_amplitude(y_out, 60.0)
    assert amp_out < 0.2 * amp_in, f"60 Hz {amp_in:.4f} -> {amp_out:.4f}"


async def test_auto_clean_skips_hum_removal_on_clean_audio(server, tmp_path):
    in_path = tmp_path / "clean.wav"
    out_path = tmp_path / "cleaned.wav"
    make_signal(in_path)

    result = await server.auto_clean_recording(
        str(in_path), str(out_path), steps_override=OTHER_STEPS_OFF
    )
    assert result["status"] == "success", result
    assert all(s["step"] != "hum_removal" for s in result["steps_applied"])
    assert result["recommendations_followed"]["hum_removal"] is False
