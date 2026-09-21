"""The pitch gate's *property*, not its numbers (issue #91).

``correct_pitch`` has two halves that must agree: ``analyze()`` decides whether
to put a "Pull the notes to pitch" card on the review queue, and ``apply()``
decides whether to actually correct note by note. They used to measure the same
two statistics on **different scopes** -- analyze over the loudest 20 s window at
22.05 kHz, apply over the whole file at native rate -- against one pair of
constants calibrated on the first. A stem could clear the gate on its loudest
passage and miss it across a song full of instrumental stretches, so the queue
recommended a fix with measured numbers on the card and the render then handed
the producer back unchanged audio.

Measured over the catalog's 66 separated stems, that hit 6 of the 15 stems the
analysis recommended.

These tests pin the **property** -- anything recommended is something ``apply()``
will run per-note -- rather than any particular threshold, because the property
is what kept breaking. A recalibration that reopens the gap fails here.
"""

import sys
from pathlib import Path

import librosa
import numpy as np
import pytest
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.production.analysis import (  # noqa: E402
    PITCH_MIN_VOICED_CONFIDENCE,
    PITCH_MIN_VOICED_RATIO,
    detect_pitch_issues,
    measure_monophony,
    passes_monophony_gate,
)
from src.production.big_flavor_mcp import BigFlavorMCPServer  # noqa: E402

SR = 22050


@pytest.fixture
def server():
    return BigFlavorMCPServer()


def _tone(midi: float, dur: float) -> np.ndarray:
    """A sung-ish note: a few harmonics with a soft attack/release, so pyin
    locks on the way it does on a real vocal rather than on a bare sine."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    hz = 440.0 * 2 ** ((midi - 69) / 12.0)
    tone = (
        np.sin(2 * np.pi * hz * t)
        + 0.3 * np.sin(2 * np.pi * hz * 2 * t)
        + 0.15 * np.sin(2 * np.pi * hz * 3 * t)
    )
    env = np.ones(n)
    ramp = int(0.03 * SR)
    env[:ramp] = np.linspace(0, 1, ramp)
    env[-ramp:] = np.linspace(1, 0, ramp)
    return tone * env


# A short phrase with most notes a third of a semitone flat -- enough for
# analyze() to clear its "worth recommending" ratio.
_PHRASE = [60.4, 62.35, 64.0, 65.4, 67.35, 65.0, 64.4, 62.35]


def _sung_passage(seconds: float) -> np.ndarray:
    """``seconds`` of continuous singing."""
    per = 0.7
    reps = int(np.ceil(seconds / (per * len(_PHRASE))))
    return np.concatenate(
        [_tone(m, per) for _ in range(reps) for m in _PHRASE]
    )[: int(seconds * SR)]


def _instrumental(seconds: float, rng: np.random.Generator) -> np.ndarray:
    """``seconds`` of the stem sitting out: low-level unpitched bleed, which is
    what a Demucs vocal stem actually contains between the vocal lines."""
    return rng.standard_normal(int(seconds * SR)) * 0.004


def write_vocal_with_long_instrumental(path: Path) -> None:
    """The failure mode this issue is about, as a file.

    A clean sung passage surrounded by long instrumental stretches: emphatically
    a single line where it plays, and voiced nowhere near often enough across
    the whole file. This is the shape of every real stem in the measured set
    that broke -- e.g. song 942's vocal stem, 0.94 voiced over its loudest 20 s
    and 0.45 across the file.
    """
    rng = np.random.default_rng(11)
    y = np.concatenate([
        _instrumental(45.0, rng),
        _sung_passage(25.0),
        _instrumental(45.0, rng),
    ])
    y = (y / np.max(np.abs(y)) * 0.8).astype(np.float32)
    sf.write(str(path), y, SR)


def _whole_file_voicing(path: Path):
    """What ``apply()`` used to gate on: pyin across the entire file."""
    y, sr = librosa.load(str(path), sr=None, mono=True)
    _f0, voiced_flag, voiced_prob = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
    )
    ratio = float(np.mean(voiced_flag)) if len(voiced_flag) else 0.0
    conf = float(np.mean(voiced_prob[voiced_flag])) if ratio > 0 else 0.0
    return ratio, conf


def test_fixture_really_does_reproduce_the_failure_mode(tmp_path):
    """Guard the guard.

    The property tests below are only worth anything if this source genuinely
    passes the windowed measurement and fails the whole-file one. If a future
    change to the fixture (or to pyin) made it clear both, the tests would still
    go green while covering nothing -- so assert the gap itself.
    """
    path = tmp_path / "vocal_sparse.wav"
    write_vocal_with_long_instrumental(path)

    y, sr = librosa.load(str(path), sr=None, mono=True)
    windowed, _f0, _flag = measure_monophony(y, sr)
    assert passes_monophony_gate(windowed), (
        f"fixture no longer clears the gate on its loudest window: {windowed}"
    )

    file_ratio, _file_conf = _whole_file_voicing(path)
    assert file_ratio < PITCH_MIN_VOICED_RATIO, (
        "fixture no longer reproduces the scope gap -- it clears the whole-file "
        f"ratio too ({file_ratio:.3f} >= {PITCH_MIN_VOICED_RATIO}), so these "
        "tests would pass without exercising the bug"
    )


async def test_recommended_pitch_fix_is_always_run_per_note(server, tmp_path):
    """The property: what the queue recommends, the render performs.

    Exercises the issue's own failure mode -- a source that passes the window
    measurement and fails the whole-file one. Before the gate was shared, this
    returned ``global_fallback`` with ``semitones=0``: a render that gave the
    producer their audio back byte for byte.
    """
    path = tmp_path / "vocal_sparse.wav"
    out = tmp_path / "out.wav"
    write_vocal_with_long_instrumental(path)

    analysis = await server.analyze_tool("correct_pitch", {"file_path": str(path)})
    assert analysis["status"] == "success", analysis
    assert analysis["recommended"] is True, analysis

    result = await server.correct_pitch(
        str(path), semitones=0, output_path=str(out),
        **{k: v for k, v in analysis["params"].items()
           if k in ("auto_tune", "chromatic", "key")},
    )
    assert result["status"] == "success", result
    assert result.get("mode") == "per_note", (
        "analysis recommended a pitch fix that apply() then declined to run "
        f"note-by-note: {result.get('fallback_reason')}"
    )
    assert result["notes_corrected"] > 0, result


async def test_apply_refuses_exactly_when_the_shared_gate_says_so(server, tmp_path):
    """Both halves ask one helper, so neither can drift from the other.

    Checked across sources that land on both sides of the gate: whatever
    ``passes_monophony_gate`` says about the audio is what ``apply()`` does with
    it. This is the structural half of the fix -- the reason a future
    recalibration cannot reopen the gap is that there is only one measurement to
    recalibrate.
    """
    rng = np.random.default_rng(3)
    sources = {}

    sung = tmp_path / "sung.wav"
    write_vocal_with_long_instrumental(sung)
    sources["vocal with long instrumental"] = sung

    noise = tmp_path / "noise.wav"
    sf.write(str(noise), (rng.standard_normal(int(30.0 * SR)) * 0.3).astype(np.float32), SR)
    sources["unpitched noise"] = noise

    quiet = tmp_path / "mostly_silent.wav"
    sf.write(str(quiet), _instrumental(30.0, rng).astype(np.float32), SR)
    sources["near-silent bleed"] = quiet

    for label, path in sources.items():
        y, sr = librosa.load(str(path), sr=None, mono=True)
        stats, _f0, _flag = measure_monophony(y, sr)
        expected_per_note = passes_monophony_gate(stats)

        out = tmp_path / f"out_{path.stem}.wav"
        result = await server.correct_pitch(
            str(path), semitones=0, auto_tune=True, chromatic=True,
            output_path=str(out),
        )
        assert result["status"] == "success", (label, result)

        if expected_per_note:
            # It may still fall back for want of stable notes, but never for
            # monophony -- that is the decision the shared helper owns.
            assert "does not look like a single line" not in (
                result.get("fallback_reason") or ""
            ), (label, stats, result)
        else:
            assert result.get("mode") == "global_fallback", (label, stats, result)


async def test_analysis_reports_the_numbers_the_gate_actually_used(tmp_path):
    """The card shows what the decision was made on.

    ``detect_pitch_issues`` reports ``voiced_ratio``/``voiced_confidence`` onto
    the fix card, and the gate compares those same rounded figures -- so a
    producer reading 0.18 against a documented threshold of 0.18 is not looking
    at a refusal.
    """
    path = tmp_path / "vocal_sparse.wav"
    write_vocal_with_long_instrumental(path)

    y, sr = librosa.load(str(path), sr=None, mono=True)
    stats, _f0, _flag = measure_monophony(y, sr)
    findings = detect_pitch_issues(y, sr)

    assert findings["voiced_ratio"] == stats["voiced_ratio"]
    assert findings["voiced_confidence"] == stats["voiced_confidence"]
    assert findings["analyzed_seconds"] == stats["analyzed_seconds"]
    assert findings["monophonic"] is passes_monophony_gate(stats)


def test_gate_constants_are_only_meaningful_on_the_shared_measurement():
    """A cheap pin on the documented calibration.

    These are the values the 66-stem measurement in #91 was run against; the
    note above them in ``analysis.py`` is what justifies them. If someone
    changes a number, this fails and sends them to that note -- which asks for a
    measurement, not a guess.
    """
    assert PITCH_MIN_VOICED_RATIO == 0.6
    assert PITCH_MIN_VOICED_CONFIDENCE == 0.18
