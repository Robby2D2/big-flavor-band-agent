"""
Assert-based tests for beat-level tempo correction (#69).

These synthesize click tracks so they exercise, without touching any database,
LLM, or real catalog file:
  * beat-grid correction (a few deliberately jittered beats are measurably
    pulled toward the target grid) — unlike whole-file match_tempo,
  * a steady, correctly-timed track left effectively unchanged at low strength,
  * the shared time map (the same map applied to a "stem set" keeps the stems in
    sync with each other),
  * the strength=0 no-op and the low-confidence "uncorrectable" guard,
  * and that whole-file match_tempo still works unchanged.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.production.big_flavor_mcp import (  # noqa: E402
    BigFlavorMCPServer,
    _detect_beats,
    _target_grid,
    _build_time_map,
    _to_mono,
)

SR = 22050


def click(times, dur, sr=SR):
    """A mono click track: a short decaying blip at each beat time (seconds)."""
    n = int(dur * sr)
    y = np.zeros(n, dtype=np.float32)
    blip_len = int(0.02 * sr)
    env = np.exp(-np.linspace(0, 8, blip_len))
    tone = np.sin(2 * np.pi * 1500 * np.arange(blip_len) / sr) * env
    for t in times:
        s = int(t * sr)
        e = min(n, s + blip_len)
        if s < n:
            y[s:e] += tone[: e - s]
    peak = np.max(np.abs(y))
    if peak > 0:
        y = (y / peak * 0.9).astype(np.float32)
    return y


def detected_beat_times(y, sr=SR):
    _, beats, _ = _detect_beats(_to_mono(y), sr)
    return beats


@pytest.fixture
def server():
    return BigFlavorMCPServer()


# --------------------------------------------------------------- unit helpers

def test_target_grid_fixed_bpm_is_isochronous():
    beats = np.array([0.0, 0.51, 1.02, 1.55, 2.0])
    grid = _target_grid(beats, target_bpm=120.0)  # 0.5s spacing
    spacing = np.diff(grid)
    assert np.allclose(spacing, 0.5, atol=1e-9), spacing
    assert grid[0] == beats[0]


def test_target_grid_smooths_a_jittered_interval():
    # Steady 0.5s beats with one interval rushed (short) then dragged (long).
    beats = np.array([0.0, 0.5, 0.9, 1.5, 2.0])
    grid = _target_grid(beats, target_bpm=None)
    intervals = np.diff(grid)
    # The smoothed intervals are less spread out than the raw jittered ones.
    assert np.std(intervals) < np.std(np.diff(beats)), (intervals, np.diff(beats))


def test_build_time_map_strength_scales_the_move():
    beats = np.array([0.0, 0.6, 1.0])
    grid = np.array([0.0, 0.5, 1.0])
    _, dst_full = _build_time_map(beats, grid, strength=1.0)
    _, dst_half = _build_time_map(beats, grid, strength=0.5)
    _, dst_zero = _build_time_map(beats, grid, strength=0.0)
    assert np.allclose(dst_full, grid)          # full quantize lands on the grid
    assert np.allclose(dst_zero, beats)         # zero leaves beats where they were
    # Half moves the middle beat halfway from 0.6 toward 0.5 → 0.55.
    assert abs(dst_half[1] - 0.55) < 1e-9, dst_half


# ----------------------------------------------------- beat-grid correction

async def test_jittered_beats_move_toward_the_grid(server, tmp_path):
    # 12 beats at a steady 120 BPM (0.5s) with two beats deliberately off-grid.
    # A longer run lets beat_track lock onto the true tempo reliably.
    base = np.arange(12) * 0.5 + 0.4
    jittered = base.copy()
    jittered[4] += 0.09   # rushes late
    jittered[7] -= 0.08   # drags early
    in_path = tmp_path / "jittered.wav"
    out_path = tmp_path / "corrected.wav"
    sf.write(str(in_path), click(jittered, dur=base[-1] + 0.6), SR)

    result = await server.correct_beats(
        str(in_path), str(out_path), strength=1.0, target_bpm=120.0
    )
    assert result["status"] == "success", result
    assert result["mode"] == "beat_grid", result
    assert result["beats_detected"] >= 8, result
    assert result["beat_confidence"], result
    # Correcting off-grid beats must actually move something.
    assert result["max_shift_ms"] > 10.0, result

    # The tool's own detected beats must be closer to the target grid after
    # correction: measure the spread of inter-beat intervals (a fixed grid has
    # constant intervals, so a smaller spread == closer to the grid).
    before = float(np.std(np.diff(detected_beat_times(sf.read(str(in_path))[0]))))
    after = float(np.std(np.diff(detected_beat_times(sf.read(str(out_path))[0]))))
    assert after < before, f"beats not more regular: before={before}, after={after}"


async def test_steady_track_unchanged_at_low_strength(server, tmp_path):
    steady = np.arange(8) * 0.5 + 0.3  # perfectly on a 120 BPM grid
    in_path = tmp_path / "steady.wav"
    out_path = tmp_path / "out.wav"
    y_in = click(steady, dur=4.5)
    sf.write(str(in_path), y_in, SR)

    result = await server.correct_beats(
        str(in_path), str(out_path), strength=0.1, target_bpm=120.0
    )
    assert result["status"] == "success", result
    # A steady track is barely moved (sub-millisecond) at low strength.
    assert result["max_shift_ms"] < 20.0, result

    y_out, _ = sf.read(str(out_path))
    # Length is essentially preserved (no wholesale stretching of a good take).
    assert abs(len(y_out) - len(y_in)) < 0.02 * SR, (len(y_out), len(y_in))


async def test_strength_zero_is_a_noop(server, tmp_path):
    beats = np.arange(8) * 0.5 + 0.3
    beats[4] += 0.06
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    y_in = click(beats, dur=4.5)
    sf.write(str(in_path), y_in, SR)

    result = await server.correct_beats(
        str(in_path), str(out_path), strength=0.0, target_bpm=120.0
    )
    assert result["status"] == "success", result
    assert result["max_shift_ms"] == 0.0, result

    y_out, _ = sf.read(str(out_path))
    # strength 0 = identity: output matches input sample-for-sample (length).
    assert len(y_out) == len(y_in), (len(y_out), len(y_in))


# --------------------------------------------------------- shared time map (#67)

async def test_shared_time_map_keeps_stems_in_sync(server, tmp_path):
    """Correct a drum stem, then apply the SAME returned time map to a second
    stem — the two stems must land their beats at the same corrected times."""
    beats = np.arange(8) * 0.5 + 0.3
    beats[3] += 0.08
    drum_in = tmp_path / "drum.wav"
    drum_out = tmp_path / "drum_out.wav"
    sf.write(str(drum_in), click(beats, dur=4.5), SR)

    drum_result = await server.correct_beats(
        str(drum_in), str(drum_out), strength=1.0, target_bpm=120.0
    )
    assert drum_result["status"] == "success", drum_result
    time_map = drum_result["time_map"]
    assert time_map["src_times"] and time_map["dst_times"], drum_result

    # A second stem with the SAME onsets (e.g. a click doubling the drum hits).
    other_in = tmp_path / "bass.wav"
    other_out = tmp_path / "bass_out.wav"
    sf.write(str(other_in), click(beats, dur=4.5), SR)

    other_result = await server.correct_beats(
        str(other_in), str(other_out), time_map=time_map
    )
    assert other_result["status"] == "success", other_result
    assert other_result["mode"] == "shared_time_map", other_result

    # Both corrected stems must have their beats at the same times.
    drum_beats = detected_beat_times(sf.read(str(drum_out))[0])
    other_beats = detected_beat_times(sf.read(str(other_out))[0])
    common = min(len(drum_beats), len(other_beats))
    assert common >= 5, (len(drum_beats), len(other_beats))
    assert np.max(np.abs(drum_beats[:common] - other_beats[:common])) < 0.03, (
        drum_beats[:common],
        other_beats[:common],
    )


async def test_bad_time_map_is_reported(server, tmp_path):
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(str(in_path), click(np.arange(8) * 0.5 + 0.3, dur=4.5), SR)

    result = await server.correct_beats(
        str(in_path), str(out_path),
        time_map={"src_times": [0.0, 1.0], "dst_times": [0.0]},  # mismatched lengths
    )
    assert result["status"] == "error", result


# ------------------------------------------------------ uncorrectable guard

async def test_too_few_beats_copies_unchanged(server, tmp_path):
    # Near-silence: no reliable beat grid can be formed.
    in_path = tmp_path / "quiet.wav"
    out_path = tmp_path / "out.wav"
    y_in = (np.random.default_rng(0).normal(0, 1e-4, int(2.0 * SR))).astype(np.float32)
    sf.write(str(in_path), y_in, SR)

    result = await server.correct_beats(str(in_path), str(out_path), strength=1.0)
    assert result["status"] == "success", result
    assert result["mode"] == "uncorrectable", result
    assert "reason" in result
    assert Path(out_path).exists()


# ------------------------------------------------------ match_tempo unchanged

async def test_match_tempo_still_whole_file(server, tmp_path):
    beats = np.arange(8) * 0.5 + 0.3
    in_path = tmp_path / "in.wav"
    out_path = tmp_path / "out.wav"
    sf.write(str(in_path), click(beats, dur=4.5), SR)

    result = await server.match_tempo(str(in_path), 100.0, str(out_path))
    assert result["status"] == "success", result
    assert result["target_bpm"] == 100.0
    assert "stretch_ratio" in result  # whole-file behaviour, no beat grid
    assert "time_map" not in result
