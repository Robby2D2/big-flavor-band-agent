"""
Tests for per-step tunable parameters and region-scoped auto-clean (issue #77
follow-up): agent-suggested intensity per step, explicit step_params overrides,
and a region selection that scopes analysis/cleaning to a span while leaving
Normalize/Master (whole-track operations) skipped and audio outside the span
untouched.

Assert-based, synthetic sine-wave fixtures — no live DB, no LLM, no MCP
transport, matching the pattern in test_big_flavor_mcp_eq_mastering.py.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.production.big_flavor_mcp import BigFlavorMCPServer

SR = 22050


def _tone(duration: float, freq: float, amp: float, sr: int = SR) -> np.ndarray:
    t = np.arange(0, duration, 1 / sr)
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def _noisy_tone(duration: float, freq: float, amp: float, noise_amp: float, sr: int = SR) -> np.ndarray:
    rng = np.random.default_rng(0)
    return _tone(duration, freq, amp, sr) + (noise_amp * rng.standard_normal(int(duration * sr))).astype(np.float32)


def _band_mag_db(y: np.ndarray, sr: int, freq: float) -> float:
    """Peak FFT magnitude (dB) nearest ``freq`` — used to detect whether a marker tone survived."""
    spectrum = np.abs(np.fft.rfft(y))
    fft_freqs = np.fft.rfftfreq(len(y), d=1 / sr)
    idx = np.argmin(np.abs(fft_freqs - freq))
    return 20 * np.log10(spectrum[idx] + 1e-12)


@pytest.fixture
def server():
    return BigFlavorMCPServer(enable_audio_analysis=True)


# ---- normalize_audio: compression_ratio ----

@pytest.mark.asyncio
async def test_normalize_audio_default_compression_ratio_is_2_5(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _noisy_tone(2.0, 220.0, 0.3, 0.05), SR)

    result = await server.normalize_audio(str(in_path), -3.0, True, str(out_path))

    assert result["status"] == "success"
    assert result["compression_ratio"] == 2.5


@pytest.mark.asyncio
async def test_normalize_audio_honors_compression_ratio_override(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _noisy_tone(2.0, 220.0, 0.3, 0.05), SR)

    result = await server.normalize_audio(
        str(in_path), -3.0, True, str(out_path), compression_ratio=6.0
    )

    assert result["status"] == "success"
    assert result["compression_ratio"] == 6.0


@pytest.mark.asyncio
async def test_normalize_audio_no_compression_ratio_is_none(server, tmp_path):
    """apply_compression=False must not report a ratio (nothing was applied)."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _tone(1.0, 440.0, 0.3), SR)

    result = await server.normalize_audio(str(in_path), -3.0, False, str(out_path))

    assert result["status"] == "success"
    assert result["compression_ratio"] is None


# ---- analyze_and_recommend_processing: region scoping + recommended_intensity ----

@pytest.mark.asyncio
async def test_analyze_whole_file_has_recommended_intensity(server, tmp_path):
    in_path = tmp_path / "in.wav"
    sf.write(in_path, _noisy_tone(3.0, 220.0, 0.3, 0.05), SR)

    result = await server.analyze_and_recommend_processing(str(in_path))

    assert result["status"] == "success"
    recs = result["recommendations"]
    assert recs["noise_reduction"]["recommended_intensity"] in ("gentle", "moderate", "aggressive")
    assert recs["eq"]["recommended_intensity"] in ("gentle", "moderate", "aggressive")
    assert recs["normalization"]["recommended_intensity"] in ("gentle", "moderate", "aggressive")
    assert recs["mastering"]["recommended_intensity"] in ("gentle", "moderate", "aggressive")
    assert result["region"] == {"start_s": None, "end_s": None}


@pytest.mark.asyncio
async def test_analyze_region_scopes_duration_and_echoes_bounds(server, tmp_path):
    in_path = tmp_path / "in.wav"
    y = np.concatenate([
        _tone(1.0, 300.0, 0.2),
        _noisy_tone(2.0, 220.0, 0.3, 0.05),
        _tone(1.0, 300.0, 0.2),
    ])
    sf.write(in_path, y, SR)

    result = await server.analyze_and_recommend_processing(str(in_path), start_s=1.0, end_s=3.0)

    assert result["status"] == "success"
    assert result["region"] == {"start_s": 1.0, "end_s": 3.0}
    # The analyzed span is ~2s, not the whole 4s file.
    assert 1.8 <= result["duration_seconds"] <= 2.2
    # Trim points (absolute file-time) must fall inside the requested region,
    # not be re-based to 0 (issue #77 follow-up).
    assert 1.0 <= result["detected_music_start"] <= 3.0
    assert 1.0 <= result["detected_music_end"] <= 3.0


# ---- auto_clean_recording: region mode ----

@pytest.mark.asyncio
async def test_auto_clean_region_always_skips_normalize_and_master(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y = np.concatenate([
        _tone(1.0, 300.0, 0.2),
        _noisy_tone(2.0, 220.0, 0.3, 0.05),
        _tone(1.0, 300.0, 0.2),
    ])
    sf.write(in_path, y, SR)

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={
            "trim": False,
            "noise_reduction": True,
            "eq": False,
            "normalize": True,  # explicitly forced on...
            "master": True,     # ...but a region must ignore this
        },
        start_s=1.0,
        end_s=3.0,
    )

    assert result["status"] == "success"
    assert result["region"] == {"start_s": 1.0, "end_s": 3.0}
    step_names = {s["step"] for s in result["steps_applied"]}
    assert "normalize" not in step_names
    assert "mastering" not in step_names
    assert result["recommendations_followed"]["normalize"] is False
    assert result["recommendations_followed"]["mastering"] is False


@pytest.mark.asyncio
async def test_auto_clean_region_leaves_audio_outside_region_untouched(server, tmp_path):
    """Noise reduction confined to a region must not alter audio outside it —
    the safety property region scoping exists for (issue #77 follow-up)."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    before = _tone(1.0, 300.0, 0.2)  # outside the region, before start_s
    inside = _noisy_tone(2.0, 220.0, 0.3, 0.05)  # inside the region
    after = _tone(1.0, 300.0, 0.2)  # outside the region, after end_s
    y = np.concatenate([before, inside, after])
    sf.write(in_path, y, SR)

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={"trim": False, "noise_reduction": True, "eq": False},
        step_params={"noise_reduction": {"reduction_strength": 0.8}},
        start_s=1.0,
        end_s=3.0,
    )

    assert result["status"] == "success"
    y_out, sr = sf.read(out_path, dtype="float32")
    assert sr == SR
    # Length preserved (noise reduction doesn't change duration).
    assert len(y_out) == len(y)

    n_before = len(before)
    n_after = len(after)
    # Outside the region, output must be numerically unchanged.
    np.testing.assert_allclose(y_out[:n_before], before, atol=1e-3)
    np.testing.assert_allclose(y_out[-n_after:], after, atol=1e-3)


@pytest.mark.asyncio
async def test_auto_clean_trim_region_mode_does_not_delete_audio_outside_region(server, tmp_path):
    """Region-mode trim must remove silence only *within* the region — the
    whole-file crop-to-detected-span path would otherwise delete everything
    outside the region (the bug this fix addresses)."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    marker_before = _tone(0.4, 6000.0, 0.3)  # unique marker, outside the region
    silence_in_region = (0.01 * np.random.default_rng(1).standard_normal(int(0.6 * SR))).astype(np.float32)
    music_in_region = _tone(1.5, 440.0, 0.3)
    marker_after = _tone(0.4, 7000.0, 0.3)  # unique marker, outside the region
    y = np.concatenate([marker_before, silence_in_region, music_in_region, marker_after])
    sf.write(in_path, y, SR)

    region_start = len(marker_before) / SR
    region_end = (len(marker_before) + len(silence_in_region) + len(music_in_region)) / SR

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={"trim": True, "noise_reduction": False, "eq": False},
        start_s=region_start,
        end_s=region_end,
    )

    assert result["status"] == "success"
    y_out, sr = sf.read(out_path, dtype="float32")

    # Both marker tones must still be present in the output — the old
    # whole-file crop-to-detected-span logic would have deleted them.
    assert _band_mag_db(y_out, sr, 6000.0) > -20.0
    assert _band_mag_db(y_out, sr, 7000.0) > -20.0


# ---- auto_clean_recording: step_params overrides ----

@pytest.mark.asyncio
async def test_auto_clean_step_params_master_target_lufs_overrides_recommendation(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _tone(2.0, 440.0, 0.1), SR)

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={"trim": False, "noise_reduction": False, "eq": False, "normalize": False, "master": True},
        step_params={"master": {"target_lufs": -20.0}},
    )

    assert result["status"] == "success"
    mastering_step = next(s for s in result["steps_applied"] if s["step"] == "mastering")
    assert mastering_step["target_lufs"] == -20.0
    assert abs(mastering_step["actual_lufs"] - (-20.0)) < 1.5


@pytest.mark.asyncio
async def test_auto_clean_step_params_noise_reduction_strength_overrides_recommendation(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _noisy_tone(2.0, 220.0, 0.3, 0.05), SR)

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={"trim": False, "noise_reduction": True, "eq": False, "normalize": False, "master": False},
        step_params={"noise_reduction": {"reduction_strength": 0.1}},
    )

    assert result["status"] == "success"
    noise_step = next(s for s in result["steps_applied"] if s["step"] == "noise_reduction")
    assert noise_step["strength"] == 0.1


@pytest.mark.asyncio
async def test_auto_clean_step_params_normalize_target_and_ratio_override(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _noisy_tone(2.0, 220.0, 0.3, 0.05), SR)

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        steps_override={"trim": False, "noise_reduction": False, "eq": False, "normalize": True, "master": False},
        step_params={"normalize": {"target_peak_db": -6.0, "compression_ratio": 8.0}},
    )

    assert result["status"] == "success"
    norm_step = next(s for s in result["steps_applied"] if s["step"] == "normalize")
    assert norm_step["target_peak_db"] == -6.0
    assert norm_step["compression_ratio"] == 8.0


@pytest.mark.asyncio
async def test_auto_clean_without_step_params_falls_back_to_aggressiveness_scaling(server, tmp_path):
    """Backward compatibility: an aggressiveness-only call (no step_params) must
    behave exactly as before — the recommendation scaled by the multiplier."""
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(in_path, _noisy_tone(2.0, 220.0, 0.3, 0.05), SR)

    analysis = await server.analyze_and_recommend_processing(str(in_path))
    recommended_strength = analysis["recommendations"]["noise_reduction"]["recommended_strength"]

    result = await server.auto_clean_recording(
        str(in_path),
        str(out_path),
        aggressiveness="gentle",
        steps_override={"trim": False, "noise_reduction": True, "eq": False, "normalize": False, "master": False},
    )

    assert result["status"] == "success"
    noise_step = next(s for s in result["steps_applied"] if s["step"] == "noise_reduction")
    assert noise_step["strength"] == round(min(1.0, recommended_strength * 0.7), 2)
