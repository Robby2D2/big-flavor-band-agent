"""``remove_hum`` — narrow high-Q notches at mains hum + harmonics."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..region import apply_to_region, blend_strength
    from ..analysis import detect_hum, load_for_analysis, HUM_NOTCH_Q
except ImportError:
    from toolkit import AudioTool, Param, register
    from region import apply_to_region, blend_strength
    from analysis import detect_hum, load_for_analysis, HUM_NOTCH_Q

logger = logging.getLogger("big-flavor-mcp")


@register
class RemoveHum(AudioTool):
    name = "remove_hum"
    summary = "Detect and remove mains electrical hum (50/60 Hz + harmonics)."
    description = (
        "Detect and remove mains electrical hum (50 or 60 Hz fundamental and its "
        "harmonics) using narrow high-Q notch filters that leave nearby musical "
        "content intact"
    )
    takes_region = True
    takes_strength = True
    params = [
        Param("fundamental_hz", float, choices=[50, 60], label="Mains fundamental (Hz)",
              help="Mains fundamental to notch (50 or 60). Auto-detected when omitted."),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Detect mains hum (50/60 Hz fundamental + harmonics)."""
        try:
            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            detection = detect_hum(y, sr)
            return {
                "status": "success",
                "tool": self.name,
                "recommended": bool(detection["detected"]),
                "params": ({"fundamental_hz": detection["fundamental_hz"]}
                           if detection["detected"] else {}),
                "findings": {
                    "fundamental_hz": detection["fundamental_hz"],
                    "harmonics_affected": detection["harmonics_affected"],
                    "prominence_db": detection["prominence_db"],
                },
                "reason": (
                    f"Mains hum detected at {detection['fundamental_hz']:.0f} Hz "
                    f"({len(detection['harmonics_affected'])} affected frequencies)"
                    if detection["detected"] else "No mains hum detected"
                ),
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing hum: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        output_path: str,
        fundamental_hz: Optional[float] = None,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        strength: float = 1.0,
    ) -> dict:
        try:
            import shutil

            import librosa
            import numpy as np
            import soundfile as sf
            from scipy import signal

            y, sr = librosa.load(file_path, sr=None)
            detection = detect_hum(y, sr)

            if fundamental_hz is not None:
                fundamental_hz = float(fundamental_hz)
                if detection["detected"] and detection["fundamental_hz"] == fundamental_hz:
                    notch_freqs = detection["harmonics_affected"]
                else:
                    # Forced fundamental without a matching detection: notch
                    # the fundamental and its first few harmonics.
                    notch_freqs = [fundamental_hz * k for k in range(1, 5)]
            elif detection["detected"]:
                fundamental_hz = detection["fundamental_hz"]
                notch_freqs = detection["harmonics_affected"]
            else:
                shutil.copyfile(file_path, output_path)
                logger.info(f"No mains hum detected in {file_path}; copied unchanged")
                return {
                    "status": "success",
                    "hum_detected": False,
                    "input_file": file_path,
                    "output_file": output_path,
                    "message": "No mains hum detected; audio copied unchanged"
                }

            notch_freqs = [float(f) for f in notch_freqs if f < sr / 2 * 0.9]

            def dehum_process(segment: np.ndarray) -> np.ndarray:
                out = segment
                for freq in notch_freqs:
                    b, a = signal.iirnotch(freq, HUM_NOTCH_Q, fs=sr)
                    # Zero-phase filtering: no phase distortion, double attenuation
                    out = signal.filtfilt(b, a, out)
                return blend_strength(segment, out, strength)

            # De-hum the region (or the whole file when no region is given, a
            # byte-identical path).
            y_filtered, _ = apply_to_region(y, sr, start_s, end_s, dehum_process)

            sf.write(output_path, y_filtered.astype(np.float32), sr)

            residual = detect_hum(y_filtered, sr)
            logger.info(
                f"Hum removal: notched {len(notch_freqs)} frequencies "
                f"(fundamental {fundamental_hz:.0f} Hz)"
            )

            return {
                "status": "success",
                "hum_detected": True,
                "fundamental_hz": fundamental_hz,
                "harmonics_notched": notch_freqs,
                "prominence_db": detection["prominence_db"],
                "residual_hum_detected": residual["detected"],
                "input_file": file_path,
                "output_file": output_path,
                "region": {"start_s": start_s, "end_s": end_s},
                "strength": strength
            }

        except Exception as e:
            logger.error(f"Error removing hum: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
