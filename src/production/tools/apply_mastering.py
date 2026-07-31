"""``apply_mastering`` — compression + limiting to a target LUFS loudness."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _write_audio, FINAL_WAV_SUBTYPE
    from ..region import apply_to_region
    from ..analysis import measure_integrated_lufs, load_for_analysis
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _write_audio, FINAL_WAV_SUBTYPE
    from region import apply_to_region
    from analysis import measure_integrated_lufs, load_for_analysis

logger = logging.getLogger("big-flavor-mcp")


@register
class ApplyMastering(AudioTool):
    name = "apply_mastering"
    summary = "Master audio to a target loudness (louder, more polished)."
    description = "Apply professional mastering to make audio louder and more polished"
    takes_region = True
    params = [
        Param("target_loudness", float, default=-14.0, minimum=-24, maximum=-6,
              label="Target loudness (LUFS)", help="Target LUFS loudness"),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Measure integrated loudness and recommend a mastering target."""
        try:
            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            if len(y) == 0:
                return {"status": "success", "tool": self.name, "recommended": False,
                        "params": {}, "findings": {}, "reason": "Empty selection",
                        "region": {"start_s": start_s, "end_s": end_s}}

            current_lufs = measure_integrated_lufs(y, sr)
            target_lufs = -14.0
            gain = target_lufs - current_lufs
            if current_lufs >= -20:
                gain = min(gain, 12.0)  # cap gain when already fairly loud
            return {
                "status": "success",
                "tool": self.name,
                "recommended": True,
                "params": {"target_loudness": target_lufs},
                "findings": {
                    "current_lufs": round(float(current_lufs), 1),
                    "estimated_gain_db": round(float(gain), 1),
                },
                "reason": f"Measured {current_lufs:.1f} LUFS; ~{gain:+.1f} dB to reach {target_lufs:.0f} LUFS",
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing mastering: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        target_loudness: float,
        output_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
    ) -> dict:
        try:
            import librosa
            import numpy as np
            from scipy import signal

            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)

            # Measured ITU-R BS.1770 integrated loudness before any processing
            # (measured on the mono reference mix — pyloudnorm expects
            # (samples,) or (samples, channels), not librosa's
            # (channels, samples) layout).
            input_lufs = measure_integrated_lufs(_to_mono(y), sr)

            # Gain applied at the target-loudness stage, captured out of the
            # region processor for the result payload.
            applied_gain = {"value": 1.0}

            def master_process(segment: np.ndarray) -> np.ndarray:
                # Apply high-pass filter to remove rumble (sosfilt runs along the
                # last axis, so this handles mono and stereo alike)
                sos = signal.butter(4, 30, 'hp', fs=sr, output='sos')
                y_filtered = signal.sosfilt(sos, segment)
                n_samples = y_filtered.shape[-1]

                # Apply smooth RMS-based mastering compression. The gain envelope
                # is computed from the mono mix and applied to all channels
                # (linked stereo) so the stereo balance is preserved.
                frame_length = int(sr * 0.05)  # 50ms window
                hop_length = int(sr * 0.01)    # 10ms hop

                rms = librosa.feature.rms(y=_to_mono(y_filtered), frame_length=frame_length, hop_length=hop_length)[0]

                # Upsample RMS to match audio length
                rms_full = np.interp(
                    np.arange(n_samples),
                    np.arange(len(rms)) * hop_length,
                    rms
                )

                # Mastering compression parameters (more aggressive than mixing)
                threshold_db = -24.0
                ratio = 3.5
                knee_width = 6.0

                # Convert to dB
                rms_db = 20 * np.log10(rms_full + 1e-10)

                # Soft-knee compression curve
                def compress_db(level_db):
                    if level_db < (threshold_db - knee_width / 2):
                        return level_db
                    elif level_db > (threshold_db + knee_width / 2):
                        return threshold_db + (level_db - threshold_db) / ratio
                    else:
                        # Smooth transition in knee region
                        x = level_db - threshold_db + knee_width / 2
                        return level_db + ((1 / ratio - 1) * (x ** 2)) / (2 * knee_width)

                compressed_db = np.array([compress_db(db) for db in rms_db])

                # Calculate gain reduction
                gain_reduction = librosa.db_to_amplitude(compressed_db - rms_db)

                # Apply attack/release smoothing
                attack_samples = int(sr * 0.003)   # 3ms attack (fast for mastering)
                release_samples = int(sr * 0.1)    # 100ms release (slow for smooth)

                smoothed_gain = np.copy(gain_reduction)
                for i in range(1, len(smoothed_gain)):
                    if gain_reduction[i] < smoothed_gain[i - 1]:
                        # Attack (gaining down)
                        alpha = 1.0 - np.exp(-1.0 / attack_samples)
                    else:
                        # Release (gaining up)
                        alpha = 1.0 - np.exp(-1.0 / release_samples)
                    smoothed_gain[i] = alpha * gain_reduction[i] + (1 - alpha) * smoothed_gain[i - 1]

                # Apply compression
                y_compressed = y_filtered * smoothed_gain

                # Gain needed to hit target_loudness, from the *measured* BS.1770
                # loudness of the compressed signal.
                compressed_lufs = measure_integrated_lufs(_to_mono(y_compressed), sr)
                gain_db = target_loudness - compressed_lufs
                gain = librosa.db_to_amplitude(gain_db)

                # Apply gain to reach target with safety margin
                peak_compressed = np.max(np.abs(y_compressed))
                if peak_compressed > 0:
                    # Add safety headroom to prevent clipping
                    max_gain = 0.9 / (peak_compressed + 1e-10)
                    gain = min(gain, max_gain)
                    y_gained = y_compressed * gain
                else:
                    y_gained = y_compressed
                    gain = 1.0

                applied_gain["value"] = gain

                # Apply smooth brick-wall limiter (prevents clipping completely)
                # Use lookahead for transparent limiting
                lookahead_ms = 5
                lookahead_samples = int(sr * lookahead_ms / 1000)

                # Create envelope of absolute values with lookahead. For stereo the
                # envelope tracks the loudest channel so one shared limiter gain
                # preserves the balance.
                abs_signal = np.max(np.abs(y_gained), axis=0) if y_gained.ndim > 1 else np.abs(y_gained)
                # Pad for lookahead
                abs_padded = np.pad(abs_signal, (0, lookahead_samples), mode='edge')

                # Find maximum in lookahead window
                from scipy.ndimage import maximum_filter
                envelope = maximum_filter(abs_padded, size=lookahead_samples)[:n_samples]

                # Calculate limiting gain (only reduce, never boost)
                limit_threshold = 0.95  # -0.5dB headroom
                limit_gain = np.where(envelope > limit_threshold, limit_threshold / (envelope + 1e-10), 1.0)

                # Smooth the gain reduction to avoid artifacts
                release_samples_limiter = int(sr * 0.05)  # 50ms release
                smoothed_limit_gain = np.copy(limit_gain)
                for i in range(1, len(smoothed_limit_gain)):
                    if limit_gain[i] < smoothed_limit_gain[i - 1]:
                        # Instant attack for limiting
                        smoothed_limit_gain[i] = limit_gain[i]
                    else:
                        # Smooth release
                        alpha = 1.0 - np.exp(-1.0 / release_samples_limiter)
                        smoothed_limit_gain[i] = alpha * limit_gain[i] + (1 - alpha) * smoothed_limit_gain[i - 1]

                # Apply limiter
                return y_gained * smoothed_limit_gain

            # Master the region (or the whole file when no region is given, a
            # byte-identical path) and splice it back with crossfaded seams.
            y_mastered, _ = apply_to_region(y, sr, start_s, end_s, master_process)
            gain = applied_gain["value"]

            # Save output at the deliberate master bit depth (WAV only —
            # other containers keep their format default subtype)
            master_subtype = FINAL_WAV_SUBTYPE if output_path.lower().endswith(".wav") else None
            _write_audio(output_path, y_mastered, sr, subtype=master_subtype)

            # Measured ITU-R BS.1770 integrated loudness of the final output
            # (mono reference mix — see input_lufs above).
            final_lufs = measure_integrated_lufs(_to_mono(y_mastered), sr)

            logger.info(f"Mastering complete: {file_path} → {output_path}")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "target_loudness_lufs": float(target_loudness),
                "input_loudness_lufs": round(float(input_lufs), 1),
                "actual_loudness_lufs": round(float(final_lufs), 1),
                "gain_applied_db": round(float(20 * np.log10(gain)), 1) if gain > 0 else 0,
                "output_bit_depth": "24-bit PCM" if master_subtype else "format default",
                "region": {"start_s": start_s, "end_s": end_s}
            }

        except Exception as e:
            logger.error(f"Error applying mastering: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
