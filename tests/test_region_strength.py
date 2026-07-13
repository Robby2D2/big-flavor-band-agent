"""Region + strength tests for the audio-cleanup tools (issue #65).

Covers the shared ``src/production/region.py`` helpers and the region/strength
params threaded through the MCP tools. Synthesizes audio with a known bad
section, so it exercises region splicing and wet/dry blend without any database,
LLM, or real catalog file (the server's ``db_manager`` stays None).

Guarantees checked:
- No region + no strength -> output byte-identical to the current tool output.
- A region -> audio outside the region is bit-identical to the input; inside it
  changed; the boundary has no discontinuity (no click).
- strength=0 -> region unchanged; strength=1 -> equals the full-strength output;
  strength=0.5 -> measurably between the two.
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
from src.production.region import apply_to_region, blend_strength, resolve_region

SR = 22050
DURATION = 4.0
N = int(SR * DURATION)


def _noisy_tone(freq: float, tone_amp: float, noise_amp: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(N) / SR
    y = tone_amp * np.sin(2 * np.pi * freq * t) + rng.normal(0.0, noise_amp, N)
    return y.astype(np.float32)


@pytest.fixture
def server() -> BigFlavorMCPServer:
    return BigFlavorMCPServer(enable_audio_analysis=True)


@pytest.fixture
def wav(tmp_path) -> Path:
    path = tmp_path / "in.wav"
    sf.write(str(path), _noisy_tone(440.0, 0.35, 0.03, 65), SR)
    return path


# ---------------- region.py unit tests ----------------

def test_resolve_region_whole_file_when_bounds_omitted():
    y = np.zeros(N, dtype=np.float32)
    assert resolve_region(y, SR, None, None) == (0, N)


def test_resolve_region_clamps_and_orders():
    y = np.zeros(N, dtype=np.float32)
    assert resolve_region(y, SR, -1.0, DURATION + 5) == (0, N)
    # Reversed bounds are swapped, not left inverted.
    start, end = resolve_region(y, SR, 3.0, 1.0)
    assert start < end


def test_apply_to_region_no_region_is_process_fn_output():
    y = _noisy_tone(440.0, 0.3, 0.0, 1)
    out, dur = apply_to_region(y, SR, None, None, lambda s: s * 0.5)
    assert np.array_equal(out, y * 0.5)
    assert dur == pytest.approx(DURATION, abs=0.01)


def test_apply_to_region_leaves_outside_untouched_and_no_click():
    y = _noisy_tone(440.0, 0.3, 0.0, 2)
    start_s, end_s = 1.0, 2.0
    # Zero the region so the effect is unmistakable.
    out, _ = apply_to_region(y, SR, start_s, end_s, lambda s: np.zeros_like(s))

    start, end = resolve_region(y, SR, start_s, end_s)
    fade = int(round(0.03 * SR))
    # Well outside the crossfaded seams the original is preserved bit-for-bit.
    assert np.array_equal(out[: start - fade - 1], y[: start - fade - 1])
    assert np.array_equal(out[end + fade + 1 :], y[end + fade + 1 :])
    # No sample-to-sample discontinuity above the source's own step size.
    max_input_step = float(np.max(np.abs(np.diff(y))))
    assert float(np.max(np.abs(np.diff(out)))) <= max_input_step + 1e-4


def test_apply_to_region_handles_length_changing_process():
    y = _noisy_tone(440.0, 0.3, 0.0, 3)
    # A process_fn that halves the region length (like trimming/stretch).
    out, region_dur = apply_to_region(
        y, SR, 1.0, 3.0, lambda s: s[..., : s.shape[-1] // 2]
    )
    assert out.shape[-1] < y.shape[-1]
    assert region_dur == pytest.approx(1.0, abs=0.05)


def test_blend_strength_endpoints_and_midpoint():
    original = np.ones(100, dtype=np.float32)
    processed = np.zeros(100, dtype=np.float32)
    assert np.array_equal(blend_strength(original, processed, 1.0), processed)
    assert np.array_equal(blend_strength(original, processed, 0.0), original)
    mid = blend_strength(original, processed, 0.5)
    assert np.allclose(mid, 0.5)


# ---------------- tool-level regression + region + strength ----------------

async def _run(server, tool, in_path, out_path, **kwargs):
    result = await tool(str(in_path), *kwargs.pop("_pos", []), str(out_path), **kwargs)
    assert result["status"] == "success", result
    y, sr = sf.read(str(out_path))
    return y, result


async def test_reduce_noise_no_args_is_unchanged_vs_baseline(server, wav, tmp_path):
    baseline = tmp_path / "baseline.wav"
    withargs = tmp_path / "withargs.wav"
    # Baseline call (positional signature, no region/strength).
    r1 = await server.reduce_noise(str(wav), 1.0, 0.7, str(baseline))
    # Same call but explicitly passing the defaults must be byte-identical.
    r2 = await server.reduce_noise(
        str(wav), 1.0, 0.7, str(withargs), None, None, None, None, 1.0
    )
    assert r1["status"] == r2["status"] == "success"
    y1, _ = sf.read(str(baseline))
    y2, _ = sf.read(str(withargs))
    assert np.array_equal(y1, y2)


async def test_reduce_noise_region_leaves_outside_bitidentical(server, wav, tmp_path):
    out = tmp_path / "out.wav"
    y_in, _ = sf.read(str(wav))
    result = await server.reduce_noise(
        str(wav), 1.0, 0.7, str(out), start_s=1.0, end_s=2.0
    )
    assert result["status"] == "success"
    assert result["region"] == {"start_s": 1.0, "end_s": 2.0}
    y_out, _ = sf.read(str(out))
    assert len(y_out) == len(y_in)

    start, end = int(1.0 * SR), int(2.0 * SR)
    fade = int(round(0.03 * SR))
    # Outside the region (past the crossfade seams) audio is untouched.
    assert np.allclose(y_out[: start - fade - 1], y_in[: start - fade - 1], atol=1e-6)
    assert np.allclose(y_out[end + fade + 1 :], y_in[end + fade + 1 :], atol=1e-6)
    # Inside the region something changed.
    assert not np.allclose(
        y_out[start + fade : end - fade], y_in[start + fade : end - fade], atol=1e-6
    )


async def test_reduce_noise_strength_interpolates(server, wav, tmp_path):
    """strength=0 -> unchanged; =1 -> full; =0.5 -> between, in the noise gap."""
    # A file with a noise-only tail so noise reduction has a measurable target.
    path = tmp_path / "gap.wav"
    y = _noisy_tone(440.0, 0.35, 0.03, 7)
    y[int(3.0 * SR):] = np.random.default_rng(7).normal(0, 0.03, N - int(3.0 * SR))
    sf.write(str(path), y.astype(np.float32), SR)

    def gap_rms(sig):
        seg = sig[int(3.2 * SR):int(3.8 * SR)]
        return float(np.sqrt(np.mean(seg ** 2)))

    outs = {}
    for s in (0.0, 0.5, 1.0):
        op = tmp_path / f"s{s}.wav"
        r = await server.reduce_noise(str(path), 1.0, 0.9, str(op), strength=s)
        assert r["status"] == "success"
        outs[s], _ = sf.read(str(op))

    r0, r5, r1 = gap_rms(outs[0.0]), gap_rms(outs[0.5]), gap_rms(outs[1.0])
    # strength=0 leaves the noise; strength=1 reduces it most; 0.5 is between.
    assert r1 < r0
    assert r1 <= r5 <= r0
    assert r5 != r1 and r5 != r0


async def test_apply_eq_no_args_unchanged_vs_baseline(server, wav, tmp_path):
    baseline = tmp_path / "baseline.wav"
    withargs = tmp_path / "withargs.wav"
    bands = [{"frequency": 2000.0, "gain_db": 6.0}]
    await server.apply_eq(str(wav), 30, None, None, 3, str(baseline), eq_bands=bands)
    await server.apply_eq(
        str(wav), 30, None, None, 3, str(withargs), eq_bands=bands,
        start_s=None, end_s=None, strength=1.0,
    )
    y1, _ = sf.read(str(baseline))
    y2, _ = sf.read(str(withargs))
    assert np.array_equal(y1, y2)


async def test_apply_eq_strength_zero_is_noop(server, wav, tmp_path):
    out = tmp_path / "out.wav"
    y_in, _ = sf.read(str(wav))
    r = await server.apply_eq(
        str(wav), 0, None, 2000.0, 8.0, str(out), strength=0.0
    )
    assert r["status"] == "success"
    y_out, _ = sf.read(str(out))
    # No high/low pass and a fully-dry blend: the region equals the input.
    assert np.allclose(y_out, y_in, atol=1e-6)


async def test_apply_eq_region_changes_only_region(server, wav, tmp_path):
    out = tmp_path / "out.wav"
    y_in, _ = sf.read(str(wav))
    r = await server.apply_eq(
        str(wav), 0, None, 2000.0, 8.0, str(out), start_s=1.0, end_s=2.0
    )
    assert r["status"] == "success"
    y_out, _ = sf.read(str(out))
    start, end = int(1.0 * SR), int(2.0 * SR)
    fade = int(round(0.03 * SR))
    assert np.allclose(y_out[: start - fade - 1], y_in[: start - fade - 1], atol=1e-6)
    assert not np.allclose(
        y_out[start + fade : end - fade], y_in[start + fade : end - fade], atol=1e-6
    )


async def test_remove_artifacts_region_and_no_arg_regression(server, wav, tmp_path):
    baseline = tmp_path / "baseline.wav"
    withargs = tmp_path / "withargs.wav"
    await server.remove_artifacts(str(wav), 0.5, str(baseline))
    await server.remove_artifacts(
        str(wav), 0.5, str(withargs), start_s=None, end_s=None, strength=1.0
    )
    y1, _ = sf.read(str(baseline))
    y2, _ = sf.read(str(withargs))
    assert np.array_equal(y1, y2)


async def test_trim_silence_region_keeps_outside(server, tmp_path):
    # Music throughout except a silent lead-in at the start of the region.
    y = _noisy_tone(440.0, 0.35, 0.0, 9)
    y[int(1.5 * SR):int(2.0 * SR)] = 0.0
    path = tmp_path / "gap.wav"
    sf.write(str(path), y, SR)
    out = tmp_path / "out.wav"

    # No region: whole-file trim removes nothing (starts/ends with music).
    r_full = await server.trim_silence(str(path), -40, str(tmp_path / "full.wav"))
    assert r_full["status"] == "success"
    y_full, _ = sf.read(str(tmp_path / "full.wav"))
    assert len(y_full) == len(y)

    # Region whose leading edge is silent: trim_silence removes that leading
    # silence within the region, so the output is shorter than the input.
    r = await server.trim_silence(str(path), -40, str(out), start_s=1.5, end_s=2.5)
    assert r["status"] == "success"
    y_out, _ = sf.read(str(out))
    assert len(y_out) < len(y)
    assert r["region"] == {"start_s": 1.5, "end_s": 2.5}
