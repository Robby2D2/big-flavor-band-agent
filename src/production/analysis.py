"""Music-analysis helpers shared by the production tools.

Key detection / note segmentation (auto-tune), beat detection + time-map
building (beat correction), and the mains-hum constants. Pure functions moved
out of ``big_flavor_mcp`` for the per-tool refactor; the server and
``src/api/routers/produce.py`` (which imports ``_detect_beats``) reach these
through ``big_flavor_mcp``'s re-exports, so those imports keep resolving.
"""

import logging
from typing import Optional

logger = logging.getLogger("big-flavor-mcp")

# Mains-hum detection/removal (issue #57)
MAINS_FUNDAMENTALS_HZ = (50.0, 60.0)
HUM_MAX_FREQ_HZ = 500.0      # harmonics above this rarely carry audible hum
HUM_PROMINENCE_DB = 10.0     # narrow peak must stand this far above the local baseline
HUM_NOTCH_Q = 30.0           # notch bandwidth = freq / Q (~2 Hz at 60 Hz)


# --------------------------------------------------------------- pitch (#68)
#
# Note-level, key-aware auto-tune. Auto-tune mode tracks a per-frame f0 curve
# (librosa.pyin), segments it into discrete note events, snaps each note toward
# the nearest tone in the detected/supplied key, and shifts only that note's
# samples — so a single wrong note is fixed without detuning the correct ones,
# unlike the old whole-file median shift.

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
_MINOR_STEPS = [0, 2, 3, 5, 7, 8, 10]  # natural minor

# Krumhansl-Schmuckler key profiles (major / minor), used to pick the key from
# the distribution of voiced pitch classes when the caller does not supply one.
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


_FLAT_TO_SHARP = {"Bb": "A#", "Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#"}


def _parse_key(key: str):
    """Parse a key string like 'C', 'A minor', 'F# major' into
    (tonic_pitch_class, is_minor). Returns None if it can't be parsed."""
    if not key:
        return None
    parts = key.strip().split()
    if not parts:
        return None
    tonic = parts[0][0].upper() + parts[0][1:]  # normalise case, keep '#'/'b'
    tonic = _FLAT_TO_SHARP.get(tonic, tonic)
    if tonic not in _NOTE_NAMES:
        return None
    is_minor = any("min" in p.lower() for p in parts[1:])
    return _NOTE_NAMES.index(tonic), is_minor


def _detect_key(pitch_classes):
    """Correlate the histogram of voiced pitch classes against the 24 major/
    minor Krumhansl profiles and return (tonic_pitch_class, is_minor)."""
    import numpy as np

    hist = np.zeros(12)
    for pc in pitch_classes:
        hist[int(pc) % 12] += 1
    if hist.sum() == 0:
        return 0, False  # default C major; caller only reaches here with voiced notes
    hist = hist / hist.sum()

    def _corr(profile, shift):
        rolled = np.roll(profile, shift)
        a = hist - hist.mean()
        b = rolled - rolled.mean()
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom else -1.0

    best_score = -2.0
    best = (0, False)
    for tonic in range(12):
        maj = _corr(np.array(_MAJOR_PROFILE), tonic)
        if maj > best_score:
            best_score, best = maj, (tonic, False)
        minr = _corr(np.array(_MINOR_PROFILE), tonic)
        if minr > best_score:
            best_score, best = minr, (tonic, True)
    return best


def _scale_midi_set(tonic_pc: int, is_minor: bool):
    """Pitch classes (0-11) that belong to the given key's diatonic scale."""
    steps = _MINOR_STEPS if is_minor else _MAJOR_STEPS
    return {(tonic_pc + s) % 12 for s in steps}


def _snap_midi(midi_value: float, chromatic: bool, scale_pcs) -> float:
    """Snap a (fractional) MIDI value to the nearest integer MIDI note. In
    key-aware mode, restrict targets to pitch classes in `scale_pcs`."""
    if chromatic:
        return float(round(midi_value))
    base = int(round(midi_value))
    # Search outward for the nearest MIDI note whose pitch class is in-scale.
    best = None
    for delta in range(-6, 7):
        cand = base + delta
        if cand % 12 in scale_pcs:
            if best is None or abs(cand - midi_value) < abs(best - midi_value):
                best = cand
    return float(best if best is not None else round(midi_value))


def _segment_notes(f0, voiced_flag, min_frames: int = 5):
    """Split a per-frame f0 curve into discrete note events.

    Splits on voicing gaps and on pitch jumps larger than ~0.6 semitone. Each
    note's target pitch is the median of its own frames (robust to the pitch
    glide at note onsets). Very short segments (< `min_frames`, i.e. the
    one/two-frame slides between notes) are dropped so they neither pollute key
    detection nor get corrected independently.

    Returns a list of (start_frame, end_frame, median_midi) for voiced notes.
    """
    import numpy as np
    import librosa

    def _valid(j):
        return bool(voiced_flag[j]) and f0[j] and f0[j] > 0 and np.isfinite(f0[j])

    def _emit(start, end, out):
        seg = [float(librosa.hz_to_midi(f0[j])) for j in range(start, end) if _valid(j)]
        if end - start >= min_frames and seg:
            out.append((start, end, float(np.median(seg))))

    notes = []
    start = None
    prev_midi = None
    for i, voiced in enumerate(voiced_flag):
        cur_midi = float(librosa.hz_to_midi(f0[i])) if _valid(i) else None
        if cur_midi is None:
            if start is not None:
                _emit(start, i, notes)
                start = None
                prev_midi = None
            continue
        if start is None:
            start = i
        elif prev_midi is not None and abs(cur_midi - prev_midi) > 0.6:
            # Pitch jump → boundary between two notes.
            _emit(start, i, notes)
            start = i
        seg = [f0[j] for j in range(start, i + 1) if _valid(j)]
        prev_midi = float(np.median(librosa.hz_to_midi(np.array(seg)))) if seg else cur_midi
    if start is not None:
        _emit(start, len(voiced_flag), notes)
    return notes


# --------------------------------------------------------------- beats (#69)
#
# Beat-level tempo correction. Unlike match_tempo (which time-stretches the
# whole file to a single BPM and can't touch a section that locally rushes or
# drags), this detects beat times, builds a target grid, and stretches each
# inter-beat segment independently so a detected beat is nudged `strength` of
# the way toward its grid position. A single time map is computed per pass and
# can be re-applied across a set of stems so they stay in sync (#67).

# Reliability guard: a grid needs enough confidently-detected beats. Below this
# the tool reports the input as un-correctable rather than garbling it.
MIN_BEATS_FOR_GRID = 4
# Default per-beat strength/confidence below which we warn the caller that the
# beat detection is shaky (a performance issue no grid-nudge can fix cleanly).
LOW_BEAT_CONFIDENCE = 0.2


def _detect_beats(mono, sr: int):
    """Detect beat times (seconds) and a per-beat strength/confidence.

    Confidence is how far the onset-envelope peak at each beat stands above the
    track's baseline (median) onset energy, squashed to 0-1. It is scale- and
    loudness-invariant: a clearly-articulated downbeat towers over the baseline
    (→ near 1), while a beat that ``beat_track`` fabricated from near-silent
    noise barely exceeds it (→ near 0). That lets the caller tell a real pulse
    from a grid hallucinated over ambiguous audio.

    Returns (tempo_bpm, beat_times, beat_confidence) where beat_times and
    beat_confidence are 1-D numpy arrays of equal length.
    """
    import numpy as np
    import librosa

    onset_env = librosa.onset.onset_strength(y=mono, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr
    )
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # Baseline = a high percentile of the onset envelope. On a sparse, clearly
    # articulated track (clicks/drums) the 90th percentile is still low, so a
    # beat peak towers over it; on dense noise or a sustained tone the 90th
    # percentile sits near the peak, so beats barely exceed it. This makes the
    # ratio a scale-invariant "is this a real pulse?" signal.
    baseline = float(np.percentile(onset_env, 90)) if len(onset_env) else 0.0
    if len(beat_frames) and baseline > 0:
        strengths = onset_env[np.clip(beat_frames, 0, len(onset_env) - 1)]
        prominence = np.maximum(0.0, strengths / baseline - 1.0)
        beat_conf = prominence / (prominence + 1.0)
    elif len(beat_frames) and onset_env.max() > 0:
        # Baseline is exactly 0 (extremely sparse) but there are real peaks —
        # any nonzero beat is maximally prominent.
        strengths = onset_env[np.clip(beat_frames, 0, len(onset_env) - 1)]
        beat_conf = (strengths > 0).astype(float)
    else:
        beat_conf = np.zeros(len(beat_frames))

    tempo_bpm = float(tempo) if np.isscalar(tempo) else float(np.atleast_1d(tempo)[0])
    return tempo_bpm, np.asarray(beat_times, dtype=float), np.asarray(beat_conf, dtype=float)


def _target_grid(beat_times, target_bpm: Optional[float]):
    """Build the target beat positions for the detected beats.

    * Explicit target_bpm → a rigid isochronous grid at that tempo, anchored to
      the first detected beat.
    * Otherwise → a *smoothed* version of the performance's own tempo curve: the
      inter-beat intervals are moving-average smoothed so a locally rushed/
      dragged section is pulled back toward the surrounding feel without
      robotizing intentional tempo changes.

    Returns a numpy array of target times, same length as beat_times.
    """
    import numpy as np

    beat_times = np.asarray(beat_times, dtype=float)
    if len(beat_times) < 2:
        return beat_times.copy()

    if target_bpm and target_bpm > 0:
        interval = 60.0 / target_bpm
        return beat_times[0] + np.arange(len(beat_times)) * interval

    intervals = np.diff(beat_times)
    # Moving-average smooth the inter-beat intervals (window 3), preserving the
    # gradual tempo arc while flattening single-beat jitter.
    smoothed = intervals.copy()
    for i in range(len(intervals)):
        lo = max(0, i - 1)
        hi = min(len(intervals), i + 2)
        smoothed[i] = intervals[lo:hi].mean()
    grid = np.empty_like(beat_times)
    grid[0] = beat_times[0]
    grid[1:] = beat_times[0] + np.cumsum(smoothed)
    return grid


def _build_time_map(beat_times, grid_times, strength: float):
    """Compute the source→target time map: each detected beat moved `strength`
    of the way toward its grid position (0 = untouched, 1 = full quantize).

    Returns (src_times, dst_times) numpy arrays including the 0 and end anchors
    so a caller can stretch each inter-beat segment to the corrected spacing.
    """
    import numpy as np

    beat_times = np.asarray(beat_times, dtype=float)
    grid_times = np.asarray(grid_times, dtype=float)
    strength = float(min(1.0, max(0.0, strength)))

    dst = beat_times + (grid_times - beat_times) * strength
    # Keep the map monotonically increasing so segment stretch ratios stay
    # positive even if a heavy correction would otherwise reorder two beats.
    dst = np.maximum.accumulate(dst)
    return beat_times.copy(), dst


def _apply_time_map(mono, sr: int, src_times, dst_times):
    """Variable-rate time-stretch a signal so its src_times land on dst_times.

    Each inter-beat segment is time-stretched independently with
    librosa.effects.time_stretch (phase vocoder). The first anchor is time 0 and
    the audio after the last beat is passed through at unit rate, so total
    length changes only by the accumulated correction.
    """
    import numpy as np
    import librosa

    src = np.asarray(src_times, dtype=float)
    dst = np.asarray(dst_times, dtype=float)

    # Anchor the start at 0 so the lead-in is corrected too.
    src = np.concatenate([[0.0], src])
    dst = np.concatenate([[0.0], dst])

    pieces = []
    total = len(mono)
    for i in range(len(src) - 1):
        s0 = int(round(src[i] * sr))
        s1 = int(round(src[i + 1] * sr))
        s0 = max(0, min(s0, total))
        s1 = max(0, min(s1, total))
        if s1 <= s0:
            continue
        seg = mono[s0:s1]
        src_dur = (s1 - s0) / sr
        dst_dur = dst[i + 1] - dst[i]
        if dst_dur <= 0 or src_dur <= 0:
            pieces.append(seg)
            continue
        rate = src_dur / dst_dur  # >1 speeds up (shortens), <1 slows down
        if abs(rate - 1.0) < 1e-3:
            pieces.append(seg)
        else:
            pieces.append(librosa.effects.time_stretch(seg, rate=rate))

    # Tail after the last mapped beat, unchanged.
    last = int(round(src[-1] * sr))
    last = max(0, min(last, total))
    if last < total:
        pieces.append(mono[last:])

    if not pieces:
        return mono.copy()
    return np.concatenate(pieces)


# --------------------------------------------------------------- per-tool analyze
def load_for_analysis(file_path: str, start_s: Optional[float] = None,
                      end_s: Optional[float] = None):
    """Load a mono reference of the (optionally region-scoped) audio for a tool's
    ``analyze`` pass.

    Returns ``(y_region, sr, offset_s, duration_s)`` where ``offset_s`` is the
    region start in seconds so a tool can restore absolute-time findings, and
    ``duration_s`` is the analyzed span's length. Region bounds are clamped to
    the file the same way the DSP path's ``resolve_region`` does.
    """
    import librosa

    y, sr = librosa.load(file_path, sr=None, mono=True)
    n = len(y)
    s = int(round((start_s or 0.0) * sr)) if start_s else 0
    e = int(round(end_s * sr)) if end_s is not None else n
    s = max(0, min(s, n))
    e = max(s, min(e, n))
    y_region = y[s:e]
    return y_region, sr, s / sr, (e - s) / sr


# --------------------------------------------------------------- loudness
def measure_integrated_lufs(y: "np.ndarray", sr: int) -> float:
    """Measured ITU-R BS.1770 integrated loudness (LUFS) via pyloudnorm.

    Replaces the previous ``rms_db - 15`` guess with a real gated-loudness
    measurement. Falls back to that same RMS-based estimate only when
    pyloudnorm can't measure the clip (e.g. shorter than its 400ms analysis
    block), so callers always get a finite number back.
    """
    import numpy as np

    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(y.astype(np.float64))
        if np.isfinite(loudness):
            return float(loudness)
    except Exception as e:
        logger.warning(f"pyloudnorm measurement failed, falling back to RMS estimate: {e}")

    rms = np.sqrt(np.mean(y ** 2)) if len(y) else 0.0
    rms_db = 20 * np.log10(rms) if rms > 0 else -70.0
    return rms_db - 15


# --------------------------------------------------------------- hum (#57)
def detect_hum(y, sr) -> dict:
    """Detect mains hum: persistent narrow spectral peaks at a 50 or 60 Hz
    fundamental and its harmonics (issue #57).

    Uses the median magnitude spectrum over time so persistent components
    (hum) survive while transient musical content is suppressed. A fundamental
    counts as detected when its own peak is prominent or at least two of its
    harmonics are (hum sometimes has a weak fundamental but strong harmonics).

    Returns:
        {"detected": bool, "fundamental_hz": float | None,
         "harmonics_affected": [float], "prominence_db": {freq: dB}}
    """
    import librosa
    import numpy as np

    n_fft = 16384
    while n_fft > len(y) and n_fft > 2048:
        n_fft //= 2
    spectrum = np.median(np.abs(librosa.stft(y, n_fft=n_fft)), axis=1)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    def peak_prominence_db(freq: float) -> float:
        offset = np.abs(freqs - freq)
        band = offset <= 3.0
        baseline_band = (offset > 6.0) & (offset <= 30.0)
        if not band.any() or not baseline_band.any():
            return 0.0
        peak = spectrum[band].max()
        baseline = np.median(spectrum[baseline_band])
        return float(20 * np.log10((peak + 1e-10) / (baseline + 1e-10)))

    best = {
        "detected": False,
        "fundamental_hz": None,
        "harmonics_affected": [],
        "prominence_db": {}
    }
    best_score = 0.0
    for f0 in MAINS_FUNDAMENTALS_HZ:
        affected = []
        prominences = {}
        harmonic = f0
        while harmonic <= min(HUM_MAX_FREQ_HZ, sr / 2 - 30.0):
            prominence = peak_prominence_db(harmonic)
            if prominence >= HUM_PROMINENCE_DB:
                affected.append(harmonic)
                prominences[harmonic] = round(prominence, 1)
            harmonic += f0
        detected = f0 in affected or len(affected) >= 2
        score = sum(prominences.values())
        if detected and score > best_score:
            best = {
                "detected": True,
                "fundamental_hz": f0,
                "harmonics_affected": affected,
                "prominence_db": prominences
            }
            best_score = score
    return best


# --------------------------------------------------------------- analysis cache
def perform_audio_analysis(file_path: str) -> dict:
    """Perform audio analysis using librosa (tempo, key, energy, spectral)."""
    import librosa
    import numpy as np
    from datetime import datetime

    # Load audio file
    y, sr = librosa.load(file_path, sr=None, mono=True)

    # Calculate duration
    duration = librosa.get_duration(y=y, sr=sr)

    # Extract tempo (BPM)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(tempo)

    # Calculate energy (RMS)
    rms = librosa.feature.rms(y=y)[0]
    avg_energy = float(np.mean(rms))

    # Categorize energy level
    if avg_energy < 0.02:
        energy_level = 'low'
    elif avg_energy < 0.05:
        energy_level = 'medium'
    else:
        energy_level = 'high'

    # Estimate key using chroma features
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    key_index = int(np.argmax(np.sum(chroma, axis=1)))
    key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    estimated_key = key_names[key_index]

    # Extract spectral features
    spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
    zero_crossing_rate = librosa.feature.zero_crossing_rate(y)[0]

    analysis = {
        'bpm': round(bpm, 1),
        'key': estimated_key,
        'energy': energy_level,
        'duration_seconds': round(duration, 1),
        'spectral_features': {
            'centroid': float(np.mean(spectral_centroids)),
            'rolloff': float(np.mean(spectral_rolloff)),
            'zero_crossing_rate': float(np.mean(zero_crossing_rate))
        },
        'analysis_timestamp': datetime.now().isoformat()
    }

    logger.info(f"Analysis complete: BPM={bpm:.1f}, Key={estimated_key}, Energy={energy_level}")
    return analysis
