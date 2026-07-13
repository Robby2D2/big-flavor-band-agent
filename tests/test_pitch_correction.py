"""
Assert-based tests for note-level, key-aware auto-tune pitch correction (#68).

These synthesize monophonic tone sequences (one note deliberately off-pitch
among otherwise-correct notes) and a polyphonic chord, so they exercise:
  * per-note correction (the wrong note is pulled toward its scale tone while
    the correct notes stay materially unchanged) — unlike the old whole-file
    median shift,
  * the correction_strength (0 = no-op) convention,
  * the polyphony guard (fall back to a whole-file shift and say so),
  * and the unchanged manual `semitones`-only whole-file mode.

No database, LLM, or real catalog file is touched.
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
    _parse_key,
    _detect_key,
    _snap_midi,
    _scale_midi_set,
)

SR = 22050
NOTE_DUR = 0.7  # seconds per note


def midi_to_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12.0)


def make_tone(midi: float, dur: float = NOTE_DUR) -> np.ndarray:
    """A single sung-ish note: sine at the given (fractional) MIDI pitch with a
    short attack/release so pyin segments cleanly and there are no clicks."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * midi_to_hz(midi) * t)
    # add a couple of harmonics so pyin locks on reliably (voice-like)
    tone += 0.3 * np.sin(2 * np.pi * midi_to_hz(midi) * 2 * t)
    tone += 0.15 * np.sin(2 * np.pi * midi_to_hz(midi) * 3 * t)
    env = np.ones(n)
    ramp = int(0.03 * SR)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[-ramp:] = np.linspace(1, 0, ramp)
    return (tone * env).astype(np.float32)


def make_sequence(midis, path: Path) -> None:
    y = np.concatenate([make_tone(m) for m in midis])
    y = (y / np.max(np.abs(y)) * 0.8).astype(np.float32)
    sf.write(str(path), y, SR)


def measure_note_midi(y: np.ndarray, note_index: int, n_notes: int) -> float:
    """Median measured MIDI pitch over the central portion of one note slot."""
    import librosa

    seg_len = len(y) // n_notes
    s = note_index * seg_len + int(0.15 * seg_len)
    e = (note_index + 1) * seg_len - int(0.15 * seg_len)
    f0, voiced, _ = librosa.pyin(
        y[s:e],
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=SR,
    )
    vals = [librosa.hz_to_midi(f) for f, v in zip(f0, voiced) if v and f and f > 0]
    return float(np.median(vals))


@pytest.fixture
def server():
    return BigFlavorMCPServer()


# ------------------------------------------------------------- unit helpers

def test_parse_key_variants():
    assert _parse_key("C") == (0, False)
    assert _parse_key("A minor") == (9, True)
    assert _parse_key("F# major") == (6, False)
    assert _parse_key("Bb") == (10, False)  # flat normalised to A#
    assert _parse_key("garbage") is None


def test_scale_membership():
    c_major = _scale_midi_set(0, False)  # C D E F G A B
    assert {0, 2, 4, 5, 7, 9, 11} == c_major
    assert 1 not in c_major  # C# is out of C major


def test_snap_is_key_aware():
    scale = _scale_midi_set(0, False)  # C major, no C#/61
    # A slightly-sharp C (MIDI ~60.4) snaps to C (60) key-aware, not up to C#.
    assert _snap_midi(60.4, chromatic=False, scale_pcs=scale) == 60.0
    # A note near C# snaps to the in-scale D or C, never C# (61).
    assert _snap_midi(61.0, chromatic=False, scale_pcs=scale) in (60.0, 62.0)
    # Chromatic mode ignores the scale.
    assert _snap_midi(61.0, chromatic=True, scale_pcs=scale) == 61.0


def test_detect_c_major():
    # A run of C-major pitch classes should be detected as C major.
    tonic, is_minor = _detect_key([0, 2, 4, 5, 7, 9, 11, 0, 4, 7])
    assert (tonic, is_minor) == (0, False)


# --------------------------------------------------- per-note auto-tune (#68)

# C major scale-ish melody; the 3rd note (index 2) is sung ~0.4 semitone sharp
# — still nearest E (64), so key-aware correction should pull it back down to E
# rather than up to F.
GOOD_MIDIS = [60, 62, 64, 65, 67]        # C D E F G
OFF_INDEX = 2
OFF_MIDI = 64.4
BAD_MIDIS = [60, 62, OFF_MIDI, 65, 67]   # E sung sharp


async def test_autotune_fixes_only_the_wrong_note(server, tmp_path):
    in_path = tmp_path / "bad.wav"
    out_path = tmp_path / "fixed.wav"
    make_sequence(BAD_MIDIS, in_path)

    result = await server.correct_pitch(
        str(in_path), semitones=0, auto_tune=True, output_path=str(out_path)
    )
    assert result["status"] == "success", result
    assert result["mode"] == "per_note", result
    assert result["notes_detected"] >= len(GOOD_MIDIS) - 1, result

    y_out, _ = sf.read(str(out_path))
    n = len(BAD_MIDIS)

    # The off-pitch note is pulled toward its correct scale tone (E = 64).
    fixed_bad = measure_note_midi(y_out, OFF_INDEX, n)
    assert abs(fixed_bad - 64.0) < 0.25, f"bad note not corrected: {fixed_bad}"
    # ...and it moved meaningfully down from where it started (64.4).
    assert (OFF_MIDI - fixed_bad) > 0.2, f"bad note barely moved: {fixed_bad}"

    # The already-correct notes are materially unchanged.
    for i, expected in enumerate(GOOD_MIDIS):
        if i == OFF_INDEX:
            continue
        got = measure_note_midi(y_out, i, n)
        assert abs(got - expected) < 0.35, f"note {i}: {got} vs {expected}"


async def test_strength_zero_is_a_noop(server, tmp_path):
    in_path = tmp_path / "bad.wav"
    out_path = tmp_path / "out.wav"
    make_sequence(BAD_MIDIS, in_path)

    result = await server.correct_pitch(
        str(in_path), semitones=0, auto_tune=True,
        output_path=str(out_path), correction_strength=0.0,
    )
    assert result["status"] == "success", result
    assert result["mode"] == "per_note", result
    assert result["notes_corrected"] == 0, result

    # The off-pitch note stays off (strength 0 = untouched).
    y_out, _ = sf.read(str(out_path))
    got = measure_note_midi(y_out, OFF_INDEX, len(BAD_MIDIS))
    assert abs(got - OFF_MIDI) < 0.25, f"strength 0 changed the note: {got}"


async def test_manual_semitones_only_shifts_whole_file(server, tmp_path):
    """auto_tune off → plain whole-file transposition, unchanged behaviour."""
    in_path = tmp_path / "good.wav"
    out_path = tmp_path / "up.wav"
    make_sequence(GOOD_MIDIS, in_path)

    result = await server.correct_pitch(
        str(in_path), semitones=2, auto_tune=False, output_path=str(out_path)
    )
    assert result["status"] == "success", result
    assert result["auto_tune_enabled"] is False
    assert result["semitones_shift"] == 2.0
    assert "mode" not in result  # manual mode is the legacy path

    y_out, _ = sf.read(str(out_path))
    # Every note is shifted up by ~2 semitones.
    for i, base in enumerate(GOOD_MIDIS):
        got = measure_note_midi(y_out, i, len(GOOD_MIDIS))
        assert abs(got - (base + 2)) < 0.4, f"note {i}: {got} vs {base + 2}"


async def test_polyphonic_input_falls_back_not_garbled(server, tmp_path):
    """A sustained chord (polyphonic) must not be silently garbled: the tool
    reports a global-shift fallback so the caller can tell what happened."""
    in_path = tmp_path / "chord.wav"
    out_path = tmp_path / "out.wav"

    n = int(3.0 * SR)
    t = np.arange(n) / SR
    chord = np.zeros(n)
    for m in (60, 64, 67, 72):  # C major triad + octave
        chord += np.sin(2 * np.pi * midi_to_hz(m) * t)
    chord = (chord / np.max(np.abs(chord)) * 0.8).astype(np.float32)
    sf.write(str(in_path), chord, SR)

    result = await server.correct_pitch(
        str(in_path), semitones=0, auto_tune=True, output_path=str(out_path)
    )
    assert result["status"] == "success", result
    assert result["mode"] == "global_fallback", result
    assert "fallback_reason" in result
    assert Path(out_path).exists()


async def test_supplied_key_overrides_detection(server, tmp_path):
    in_path = tmp_path / "bad.wav"
    out_path = tmp_path / "out.wav"
    make_sequence(BAD_MIDIS, in_path)

    result = await server.correct_pitch(
        str(in_path), semitones=0, auto_tune=True,
        output_path=str(out_path), key="C major",
    )
    assert result["status"] == "success", result
    assert result["key"] == "C major"
    assert result["key_source"] == "supplied"
