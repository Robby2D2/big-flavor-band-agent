"""``apply_eq`` — high/low-pass + peaking-band equalization (zero-phase)."""

import logging
from typing import List, Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _write_audio
    from ..region import apply_to_region, blend_strength
    from ..analysis import load_for_analysis
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _write_audio
    from region import apply_to_region, blend_strength
    from analysis import load_for_analysis

logger = logging.getLogger("big-flavor-mcp")


def peaking_eq_sos(freq_hz: float, gain_db: float, sr: float, q: float = 1.5):
    """RBJ Audio EQ Cookbook peaking filter, as a single second-order section.

    A true peaking/notch biquad with a predictable gain at ``freq_hz``
    (positive ``gain_db`` boosts, negative cuts), unlike band-passing the signal
    and mixing it back in scaled — that approximation shifts phase and doesn't
    produce the requested dB change at the target frequency. At ``gain_db == 0``
    the coefficients reduce to an exact identity filter (b == a), so a "neutral"
    EQ pass is a true no-op.

    Callers always run this through ``sosfiltfilt`` (forward+backward) for
    zero-phase output, which squares the filter's magnitude response and
    therefore doubles the dB gain of a single pass. Designing for half the
    requested ``gain_db`` here means the *net* two-pass gain at ``freq_hz``
    matches what the caller asked for.
    """
    import numpy as np

    A = 10 ** ((gain_db / 2) / 40)
    w0 = 2 * np.pi * freq_hz / sr
    alpha = np.sin(w0) / (2 * q)
    cos_w0 = np.cos(w0)

    b0 = 1 + alpha * A
    b1 = -2 * cos_w0
    b2 = 1 - alpha * A
    a0 = 1 + alpha / A
    a1 = -2 * cos_w0
    a2 = 1 - alpha / A

    return np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])


@register
class ApplyEq(AudioTool):
    name = "apply_eq"
    summary = "Shape the sound with EQ (remove mud, add clarity)."
    description = "Apply equalizer filters to shape the sound (remove mud, add clarity, etc.)"
    takes_region = True
    takes_strength = True
    params = [
        Param("high_pass_freq", float, default=30, minimum=0, maximum=1000,
              label="High-pass (Hz)", help="High-pass filter frequency (removes low rumble)"),
        Param("low_pass_freq", float, label="Low-pass (Hz)",
              help="Low-pass filter frequency in Hz (removes high noise, optional)"),
        Param("boost_freq", float, label="Boost frequency (Hz)",
              help="Frequency to boost (optional; ignored if eq_bands is given)"),
        Param("boost_db", float, default=3, minimum=-24, maximum=24,
              label="Boost amount (dB)",
              help="Boost amount in dB (ignored if eq_bands is given)"),
        Param("eq_bands", list, label="EQ bands",
              help="List of peaking EQ adjustments applied together, each "
                   "{frequency (Hz), gain_db}. Takes precedence over boost_freq/boost_db.",
              schema={
                  "type": "array",
                  "items": {
                      "type": "object",
                      "properties": {
                          "frequency": {"type": "number"},
                          "gain_db": {"type": "number"},
                      },
                      "required": ["frequency", "gain_db"],
                  },
              }),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Measure the frequency balance and recommend EQ moves."""
        try:
            import numpy as np
            import librosa

            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            if len(y) == 0:
                return {"status": "success", "tool": self.name, "recommended": False,
                        "params": {}, "findings": {}, "reason": "Empty selection",
                        "region": {"start_s": start_s, "end_s": end_s}}

            D = np.abs(librosa.stft(y))
            avg_spectrum = np.mean(D, axis=1)
            freqs = librosa.fft_frequencies(sr=sr)

            bass_band = (freqs >= 20) & (freqs < 250)
            mid_band = (freqs >= 250) & (freqs < 2000)
            treble_band = (freqs >= 2000) & (freqs < 8000)
            bass_energy = np.mean(avg_spectrum[bass_band])
            mid_energy = np.mean(avg_spectrum[mid_band])
            treble_energy = np.mean(avg_spectrum[treble_band])
            total = bass_energy + mid_energy + treble_energy + 1e-12
            bass_pct = 100 * bass_energy / total
            mid_pct = 100 * mid_energy / total
            treble_pct = 100 * treble_energy / total

            adjustments = []
            high_pass_freq = None
            low_pass_freq = None
            sub_bass = (freqs >= 20) & (freqs < 60)
            sub_bass_energy = np.mean(avg_spectrum[sub_bass])
            if sub_bass_energy > bass_energy * 0.3:
                high_pass_freq = 80
                adjustments.append({"type": "high_pass", "frequency": 80,
                                    "reason": "Excessive low-frequency rumble detected"})
            elif sub_bass_energy > bass_energy * 0.2:
                high_pass_freq = 60
                adjustments.append({"type": "high_pass", "frequency": 60,
                                    "reason": "Some low-frequency rumble present"})

            eq_bands = []
            if bass_pct > 45:
                eq_bands.append({"frequency": 200, "gain_db": -3})
                adjustments.append({"type": "reduce", "frequency": 200, "amount": -3,
                                    "reason": "Bass-heavy mix, may sound muddy"})
            if treble_pct < 15:
                eq_bands.append({"frequency": 4000, "gain_db": 2})
                adjustments.append({"type": "boost", "frequency": 4000, "amount": 2,
                                    "reason": "Lacks high-frequency clarity"})
            elif treble_pct > 35:
                low_pass_freq = 12000
                adjustments.append({"type": "low_pass", "frequency": 12000,
                                    "reason": "Excessive high-frequency content (may be harsh)"})

            recommended = len(adjustments) > 0
            rec_params = {}
            if high_pass_freq is not None:
                rec_params["high_pass_freq"] = high_pass_freq
            if low_pass_freq is not None:
                rec_params["low_pass_freq"] = low_pass_freq
            if eq_bands:
                rec_params["eq_bands"] = eq_bands
            return {
                "status": "success",
                "tool": self.name,
                "recommended": recommended,
                "params": rec_params,
                "findings": {
                    "frequency_balance": {
                        "bass_percent": round(float(bass_pct), 1),
                        "mid_percent": round(float(mid_pct), 1),
                        "treble_percent": round(float(treble_pct), 1),
                    },
                    "adjustments": adjustments,
                },
                "reason": (f"{len(adjustments)} frequency imbalance(s) detected"
                           if recommended else "Frequency balance looks fine"),
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing EQ: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        high_pass_freq: float,
        low_pass_freq: Optional[float],
        boost_freq: Optional[float],
        boost_db: float,
        output_path: str,
        eq_bands: Optional[List[dict]] = None,
        subtype: Optional[str] = None,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        strength: float = 1.0,
    ) -> dict:
        try:
            import numpy as np
            from scipy import signal

            # Load audio (channel count preserved; sosfilt runs along the last
            # axis, so every filter below handles mono and stereo alike)
            y, sr = _load_audio(file_path)

            # Peaking/notch bands: every recommended boost/cut is applied in one
            # pass, not just the last one.
            bands = eq_bands if eq_bands else (
                [{"frequency": boost_freq, "gain_db": boost_db}] if boost_freq else []
            )
            filters_applied = []

            # Build the EQ filter chain once, then run it over the region (or
            # the whole file when no region is given — a byte-identical path).
            def eq_process(segment: np.ndarray) -> np.ndarray:
                out = segment.copy()

                # Apply high-pass filter (remove low rumble)
                if high_pass_freq and high_pass_freq > 0:
                    sos = signal.butter(4, high_pass_freq, 'hp', fs=sr, output='sos')
                    out = signal.sosfiltfilt(sos, out)
                    filters_applied.append(f"High-pass @ {high_pass_freq}Hz")

                # Apply low-pass filter (remove high noise)
                if low_pass_freq and low_pass_freq > 0:
                    sos = signal.butter(4, low_pass_freq, 'lp', fs=sr, output='sos')
                    out = signal.sosfiltfilt(sos, out)
                    filters_applied.append(f"Low-pass @ {low_pass_freq}Hz")

                for band in bands:
                    freq = band.get("frequency")
                    gain_db = band.get("gain_db", 0)
                    if not freq or freq <= 0 or freq >= sr / 2 or gain_db == 0:
                        continue
                    sos = peaking_eq_sos(freq, gain_db, sr)
                    out = signal.sosfiltfilt(sos, out)
                    filters_applied.append(
                        f"{'Boost' if gain_db > 0 else 'Cut'} {gain_db:+.1f}dB @ {freq}Hz"
                    )

                # Wet/dry blend so strength dials between untouched and full EQ.
                return blend_strength(segment, out, strength)

            y_filtered, _ = apply_to_region(y, sr, start_s, end_s, eq_process)

            # Normalize to prevent clipping
            peak = np.max(np.abs(y_filtered))
            if peak > 0.95:
                y_filtered = y_filtered * (0.95 / peak)

            # Save output
            _write_audio(output_path, y_filtered, sr, subtype=subtype)

            logger.info(f"EQ applied: {', '.join(filters_applied) if filters_applied else '(no-op)'}")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "filters_applied": filters_applied,
                "high_pass_freq": high_pass_freq,
                "low_pass_freq": low_pass_freq,
                "eq_bands": bands,
                "boost_freq": boost_freq,
                "boost_db": boost_db if boost_freq else 0,
                "region": {"start_s": start_s, "end_s": end_s},
                "strength": strength
            }

        except Exception as e:
            logger.error(f"Error applying EQ: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
