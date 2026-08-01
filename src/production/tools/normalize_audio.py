"""``normalize_audio`` — peak normalization + optional soft-knee compression."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _write_audio
    from ..analysis import load_for_analysis
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _write_audio
    from analysis import load_for_analysis

logger = logging.getLogger("big-flavor-mcp")


@register
class NormalizeAudio(AudioTool):
    name = "normalize_audio"
    summary = "Normalize levels and apply compression for consistent volume."
    description = "Normalize audio levels and apply compression for consistent volume"
    params = [
        Param("target_level_db", float, default=-3, minimum=-24, maximum=0,
              label="Target peak (dB)", help="Target peak level in dB"),
        Param("apply_compression", bool, default=True, label="Apply compression",
              help="Apply compression for dynamic range control"),
        Param("compression_ratio", float, default=2.5, minimum=1, maximum=10,
              label="Compression ratio",
              help="Override for the compressor's ratio (default 2.5 when omitted)"),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Measure peak level + dynamic range; recommend level/compression."""
        try:
            import numpy as np

            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            if len(y) == 0:
                return {"status": "success", "tool": self.name, "recommended": False,
                        "params": {}, "findings": {}, "reason": "Empty selection",
                        "region": {"start_s": start_s, "end_s": end_s}}

            peak = np.max(np.abs(y))
            peak_db = 20 * np.log10(peak) if peak > 0 else -np.inf
            rms_overall = np.sqrt(np.mean(y ** 2))
            crest_db = 20 * np.log10(peak / (rms_overall + 1e-10)) if rms_overall > 0 else 0.0
            if crest_db > 18:
                comp_ratio = 4.0
            elif crest_db > 14:
                comp_ratio = 3.0
            else:
                comp_ratio = 2.0

            recommended = bool(peak_db < -6 or peak_db > -1)
            deviation_db = None
            if np.isfinite(peak_db):
                if peak_db < -6:
                    deviation_db = -6 - peak_db
                elif peak_db > -1:
                    deviation_db = peak_db - (-1)
                else:
                    deviation_db = 0.0
            return {
                "status": "success",
                "tool": self.name,
                "recommended": recommended,
                "params": {"target_level_db": -3.0, "apply_compression": True,
                           "compression_ratio": float(comp_ratio)},
                "findings": {
                    "current_peak_db": round(float(peak_db), 1) if np.isfinite(peak_db) else None,
                    "crest_factor_db": round(float(crest_db), 1),
                },
                "confidence": self.confidence_tier(deviation_db, high=6.0, worth=0.0),
                "reason": (f"Peak at {peak_db:.1f} dB — level optimization recommended"
                           if recommended else "Levels are already in range"),
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing normalization: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        target_level_db: float,
        apply_compression: bool,
        output_path: str,
        subtype: Optional[str] = None,
        compression_ratio: Optional[float] = None,
    ) -> dict:
        try:
            import librosa
            import numpy as np

            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)
            n_samples = y.shape[-1]

            # Calculate current peak level
            current_peak = np.max(np.abs(y))
            current_peak_db = 20 * np.log10(current_peak) if current_peak > 0 else -np.inf

            if apply_compression:
                # Apply smooth RMS-based compression to avoid clicks. The gain
                # envelope comes from the mono mix and is shared by all channels
                # (linked stereo) so the balance is preserved.
                # Calculate RMS envelope with longer window for smoother compression
                frame_length = int(sr * 0.05)  # 50ms window
                hop_length = int(sr * 0.01)    # 10ms hop

                rms = librosa.feature.rms(y=_to_mono(y), frame_length=frame_length, hop_length=hop_length)[0]

                # Upsample RMS to match audio length
                rms_full = np.interp(
                    np.arange(n_samples),
                    np.arange(len(rms)) * hop_length,
                    rms
                )

                # Gentle compression parameters
                threshold_db = -20.0
                ratio = float(compression_ratio) if compression_ratio is not None else 2.5
                knee_width = 10.0

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

                # Calculate gain reduction in linear scale
                gain_reduction = librosa.db_to_amplitude(compressed_db - rms_db)

                # Apply attack/release smoothing to prevent clicks
                attack_samples = int(sr * 0.005)   # 5ms attack
                release_samples = int(sr * 0.05)   # 50ms release

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
                y_compressed = y * smoothed_gain
            else:
                y_compressed = y

            # Normalize to target level with headroom to prevent clipping
            target_amplitude = librosa.db_to_amplitude(target_level_db)
            peak_after_compression = np.max(np.abs(y_compressed))

            if peak_after_compression > 0:
                # Add 0.5dB safety headroom
                safety_factor = 0.94  # ~-0.5dB
                gain = (target_amplitude / peak_after_compression) * safety_factor
                y_normalized = y_compressed * gain
            else:
                y_normalized = y_compressed

            # Soft clip if needed (should rarely happen now)
            def soft_clip(x):
                # Smooth saturation curve instead of hard clip
                return np.tanh(x * 0.9) / np.tanh(0.9)

            if np.max(np.abs(y_normalized)) > 0.99:
                y_normalized = soft_clip(y_normalized)

            # Save output
            _write_audio(output_path, y_normalized, sr, subtype=subtype)

            final_peak_db = 20 * np.log10(np.max(np.abs(y_normalized)))
            gain_applied_db = final_peak_db - current_peak_db

            logger.info(f"Normalized: {current_peak_db:.1f}dB → {final_peak_db:.1f}dB")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_peak_db": round(float(current_peak_db), 1),
                "target_peak_db": float(target_level_db),
                "final_peak_db": round(float(final_peak_db), 1),
                "gain_applied_db": round(float(gain_applied_db), 1),
                "compression_applied": apply_compression,
                "compression_ratio": (
                    float(compression_ratio) if compression_ratio is not None else 2.5
                ) if apply_compression else None
            }

        except Exception as e:
            logger.error(f"Error normalizing audio: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
