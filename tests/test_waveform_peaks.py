"""Tests for the waveform drawing envelope (src/production/waveform_peaks.py).

The envelope is what the produce console draws instead of downloading and
decoding whole stem files, so the things worth pinning down are the ones a
canvas would show: the right number of buckets, amplitudes that survive
quantisation, and no value that would draw outside the canvas.
"""
import numpy as np
import pytest
import soundfile as sf

from src.production import waveform_peaks


def _write_tone(path, amplitude=0.3, seconds=1.0, sr=8000, subtype=None):
    """Write a stereo sine WAV at a known amplitude."""
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    mono = amplitude * np.sin(2 * np.pi * 220.0 * t)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    sf.write(str(path), stereo, sr, subtype=subtype)


def test_peaks_shape_duration_and_amplitude(tmp_path):
    """A known tone yields full-resolution buckets at the expected amplitude."""
    src = tmp_path / "tone.wav"
    _write_tone(src, amplitude=0.5, seconds=1.0, sr=8000)

    peaks = waveform_peaks.compute_peaks(str(src))

    assert peaks["version"] == waveform_peaks.PEAKS_FORMAT_VERSION
    assert peaks["resolution"] == waveform_peaks.PEAKS_RESOLUTION
    assert len(peaks["min"]) == len(peaks["max"]) == waveform_peaks.PEAKS_RESOLUTION
    assert peaks["duration_seconds"] == pytest.approx(1.0, abs=0.01)
    assert peaks["sample_rate"] == 8000
    assert peaks["channels"] == 2

    # 0.5 amplitude quantised against a scale of 127 -> ~64, both directions.
    expected = round(0.5 * waveform_peaks.PEAKS_SCALE)
    assert max(peaks["max"]) == pytest.approx(expected, abs=1)
    assert min(peaks["min"]) == pytest.approx(-expected, abs=1)


def test_peaks_shorter_file_truncates_resolution(tmp_path):
    """A file with fewer frames than buckets reports the smaller resolution.

    The client resamples from whatever width it is handed, so a short envelope
    is normal rather than an error — and the stem-separation fixtures
    (0.25 s at 8 kHz) sit right on this boundary.
    """
    src = tmp_path / "short.wav"
    _write_tone(src, seconds=0.05, sr=8000)  # 400 frames

    peaks = waveform_peaks.compute_peaks(str(src))

    assert peaks["resolution"] == 400
    assert len(peaks["min"]) == len(peaks["max"]) == 400
    assert all(np.isfinite(peaks["min"])) and all(np.isfinite(peaks["max"]))


def test_peaks_silence_is_a_flat_line(tmp_path):
    src = tmp_path / "silence.wav"
    sf.write(str(src), np.zeros((8000, 2), dtype=np.float32), 8000)

    peaks = waveform_peaks.compute_peaks(str(src))

    assert set(peaks["min"]) == {0}
    assert set(peaks["max"]) == {0}


def test_peaks_clip_out_of_range_samples(tmp_path):
    """Float WAVs can exceed +/-1.0; clipping keeps the draw inside the canvas.

    The produce chain writes float-subtype output (audio_io._write_audio), so
    this is a real file the console can be asked to draw, not a synthetic case.
    """
    src = tmp_path / "hot.wav"
    loud = np.full((8000, 2), 1.5, dtype=np.float32)
    loud[::2] = -1.5
    sf.write(str(src), loud, 8000, subtype="FLOAT")

    peaks = waveform_peaks.compute_peaks(str(src))

    scale = waveform_peaks.PEAKS_SCALE
    assert max(peaks["max"]) == scale
    assert min(peaks["min"]) == -scale
    assert all(-scale <= v <= scale for v in peaks["min"] + peaks["max"])


def test_peaks_empty_file_raises(tmp_path):
    src = tmp_path / "empty.wav"
    sf.write(str(src), np.zeros((0, 2), dtype=np.float32), 8000)

    with pytest.raises(ValueError):
        waveform_peaks.compute_peaks(str(src))


def test_peaks_match_a_naive_whole_file_pass(tmp_path):
    """Streaming in blocks must give the same envelope as loading it all at once.

    Guards the block-seam handling: bucket boundaries do not line up with read
    boundaries, so a run of samples for one bucket can straddle two blocks.
    """
    src = tmp_path / "long.wav"
    # Comfortably more frames than one BLOCK_FRAMES read, so seams actually occur.
    sr = 8000
    seconds = waveform_peaks.BLOCK_FRAMES * 3 / sr
    rng = np.random.default_rng(1234)
    data = rng.uniform(-0.8, 0.8, size=(int(sr * seconds), 2)).astype(np.float32)
    sf.write(str(src), data, sr, subtype="FLOAT")

    peaks = waveform_peaks.compute_peaks(str(src))

    mono = data.mean(axis=1)
    buckets = waveform_peaks.PEAKS_RESOLUTION
    index = (np.arange(len(mono), dtype=np.int64) * buckets) // len(mono)
    ref_min = np.full(buckets, np.inf, dtype=np.float32)
    ref_max = np.full(buckets, -np.inf, dtype=np.float32)
    np.minimum.at(ref_min, index, mono)
    np.maximum.at(ref_max, index, mono)

    def quantise(values):
        scaled = np.round(values * waveform_peaks.PEAKS_SCALE)
        clipped = np.clip(scaled, -waveform_peaks.PEAKS_SCALE, waveform_peaks.PEAKS_SCALE)
        return clipped.astype(np.int16).tolist()

    assert peaks["min"] == quantise(ref_min)
    assert peaks["max"] == quantise(ref_max)
