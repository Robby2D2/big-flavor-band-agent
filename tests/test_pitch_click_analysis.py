"""
Assert-based tests for the pitch and click *detection* added in issue #89.

``correct_pitch`` and ``remove_artifacts`` used to inherit the base ``analyze()``
stub, so nothing could ever recommend them. These tests synthesize their four
corners — no database, no LLM, no catalog file:

  * a tone sequence sung in tune reports no pitch problem,
  * the same sequence pushed 40 cents sharp reports notes off target, with a
    confidence and the auto-tune params pre-filled,
  * a polyphonic source is refused rather than measured (pyin tracks one pitch),
  * a clean file reports no clicks, and one with an injected discontinuity
    reports it with a sensitivity tuned to what was measured.
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.production.analysis import (  # noqa: E402
    CLICK_MIN_JUMP,
    PITCH_OFF_TARGET_CENTS,
    detect_clicks,
    detect_pitch_issues,
)
from src.production.toolkit import REGISTRY, ToolContext  # noqa: E402
import src.production.tools  # noqa: F401,E402  (registers every tool)

SR = 22050
# Long enough per note that _segment_notes keeps them (it drops runs shorter
# than 5 pyin frames) and that pyin's own voicing estimate settles.
NOTE_SECONDS = 0.7


def tone_sequence(midi_notes, cents_off=0.0, sr=SR, seconds=NOTE_SECONDS):
    """A monophonic line: one sustained tone per MIDI note, detuned by `cents_off`.

    Two harmonics rather than a bare sine — pyin's voicing confidence on a pure
    sine is borderline, and real singing is never one partial anyway.
    """
    pieces = []
    for midi in midi_notes:
        freq = 440.0 * 2 ** ((midi + cents_off / 100.0 - 69) / 12.0)
        t = np.arange(int(seconds * sr)) / sr
        wave = np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * 2 * freq * t)
        # Short fades so the note boundaries aren't discontinuities the click
        # detector would (correctly) call clicks.
        ramp = int(0.01 * sr)
        envelope = np.ones_like(wave)
        envelope[:ramp] = np.linspace(0, 1, ramp)
        envelope[-ramp:] = np.linspace(1, 0, ramp)
        pieces.append((wave * envelope).astype(np.float32))
    return np.concatenate(pieces) * 0.5


def chord(midi_notes, sr=SR, seconds=4.0):
    """Every note at once — the polyphonic case note detection cannot serve."""
    t = np.arange(int(seconds * sr)) / sr
    out = np.zeros_like(t)
    for midi in midi_notes:
        freq = 440.0 * 2 ** ((midi - 69) / 12.0)
        out += np.sin(2 * np.pi * freq * t)
    return (out / len(midi_notes) * 0.5).astype(np.float32)


def write(tmp_path, name, y, sr=SR):
    path = tmp_path / name
    sf.write(str(path), y, sr)
    return str(path)


@pytest.fixture
def ctx():
    return ToolContext(enable_audio_analysis=True)


# A C major line, so the detected key is unambiguous.
IN_KEY_LINE = [60, 62, 64, 65, 67, 65, 64, 62]


# --------------------------------------------------------------- pitch

def test_in_tune_line_reports_nothing_off_target():
    measured = detect_pitch_issues(tone_sequence(IN_KEY_LINE), SR)
    assert measured["monophonic"], measured
    assert measured["notes_detected"] >= 4, measured
    assert measured["notes_off_target"] == 0, measured
    assert measured["median_deviation_cents"] < PITCH_OFF_TARGET_CENTS, measured


def test_detuned_line_reports_its_notes_off_target():
    measured = detect_pitch_issues(tone_sequence(IN_KEY_LINE, cents_off=40.0), SR)
    assert measured["monophonic"], measured
    assert measured["notes_off_target"] == measured["notes_detected"], measured
    assert measured["off_target_ratio"] == 1.0, measured
    # Measured against each note's own nearest semitone, so 40 cents means 40.
    assert 25 < measured["median_deviation_cents"] < 55, measured


def test_unpitched_material_is_refused_not_measured():
    rng = np.random.default_rng(7)
    measured = detect_pitch_issues((rng.standard_normal(SR * 5) * 0.3).astype(np.float32), SR)
    assert not measured["monophonic"], measured
    assert measured["notes_detected"] == 0, measured


async def test_analyze_recommends_a_detuned_line_with_prefilled_params(ctx, tmp_path):
    path = write(tmp_path, "sharp.wav", tone_sequence(IN_KEY_LINE, cents_off=40.0))
    result = await REGISTRY["correct_pitch"].analyze(ctx, path)

    assert result["status"] == "success", result
    assert result["recommended"] is True, result
    assert result["confidence"] in ("high", "worth_a_listen"), result
    # The declared defaults are an exact no-op, so a recommended card has to
    # arrive in auto-tune, in the key that was measured.
    assert result["params"]["auto_tune"] is True, result
    assert result["params"]["key"] == result["findings"]["key"], result
    assert result["findings"]["key_source"] == "detected", result


async def test_analyze_stays_quiet_on_an_in_tune_line(ctx, tmp_path):
    path = write(tmp_path, "tuned.wav", tone_sequence(IN_KEY_LINE))
    result = await REGISTRY["correct_pitch"].analyze(ctx, path)

    assert result["recommended"] is False, result
    assert result["confidence"] is None, result
    assert result["params"] == {}, result


async def test_a_chord_never_produces_a_pitch_card(ctx, tmp_path):
    """pyin tracks one pitch, so a chord reads as its root — perfectly in tune.

    That is the second gate, and the one that holds on real polyphonic stems:
    measured across four songs the `other`/`guitar` stems land at 0-5% of notes
    off target, far under the ratio it takes to recommend anything.
    """
    path = write(tmp_path, "chord.wav", chord([60, 64, 67]))
    result = await REGISTRY["correct_pitch"].analyze(ctx, path)

    assert result["recommended"] is False, result
    assert result["findings"]["off_target_ratio"] == 0.0, result
    assert result["params"] == {}, result


async def test_analyze_says_unpitched_material_cannot_be_measured(ctx, tmp_path):
    rng = np.random.default_rng(7)
    path = write(tmp_path, "noise.wav", (rng.standard_normal(SR * 5) * 0.3).astype(np.float32))
    result = await REGISTRY["correct_pitch"].analyze(ctx, path)

    assert result["recommended"] is False, result
    assert result["findings"]["monophonic"] is False, result
    assert "single line" in result["reason"], result


# --------------------------------------------------------------- clicks

def clean_music(seconds=6.0, sr=SR):
    """A steady tone with vibrato — plenty of transients, no discontinuities."""
    t = np.arange(int(seconds * sr)) / sr
    y = np.sin(2 * np.pi * 220 * t) * (0.6 + 0.3 * np.sin(2 * np.pi * 3 * t))
    return (y * 0.5).astype(np.float32)


def test_clean_audio_reports_no_clicks():
    measured = detect_clicks(clean_music(), SR)
    assert measured["count"] == 0, measured
    assert measured["per_minute"] == 0.0, measured


def test_an_injected_click_is_detected():
    y = clean_music()
    y[int(2.0 * SR)] += 0.9  # a one-sample discontinuity: the definition of a click
    measured = detect_clicks(y, SR)

    assert measured["count"] >= 1, measured
    assert measured["per_minute"] > 0, measured
    assert measured["peak_jump"] > CLICK_MIN_JUMP, measured


def test_three_clicks_are_counted_separately():
    y = clean_music()
    for at in (1.0, 2.5, 4.0):
        y[int(at * SR)] += 0.9
    assert detect_clicks(y, SR)["count"] == 3, detect_clicks(y, SR)


async def test_analyze_recommends_a_sensitivity_that_matches_what_it_measured(ctx, tmp_path):
    y = clean_music()
    y[int(2.0 * SR)] += 0.9
    path = write(tmp_path, "clicky.wav", y)
    result = await REGISTRY["remove_artifacts"].analyze(ctx, path)

    assert result["recommended"] is True, result
    assert result["findings"]["count"] >= 1, result
    assert result["confidence"] in ("high", "worth_a_listen"), result
    # Nowhere near the declared 0.5, which would cut at the 90th-percentile
    # jump and interpolate a tenth of the file to repair one click.
    assert 0 < result["params"]["sensitivity"] < 0.1, result


async def test_analyze_stays_quiet_on_clean_audio(ctx, tmp_path):
    path = write(tmp_path, "clean.wav", clean_music())
    result = await REGISTRY["remove_artifacts"].analyze(ctx, path)

    assert result["recommended"] is False, result
    assert result["params"] == {}, result
    assert result["reason"] == "No clicks or pops detected", result
