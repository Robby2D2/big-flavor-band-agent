"""``remove_artifacts`` — detect and interpolate clicks/pops/glitches."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _apply_per_channel, _write_audio
    from ..region import apply_to_region, blend_strength
    from ..analysis import detect_clicks, load_for_analysis, CLICK_HIGH_PER_MIN
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _apply_per_channel, _write_audio
    from region import apply_to_region, blend_strength
    from analysis import detect_clicks, load_for_analysis, CLICK_HIGH_PER_MIN

logger = logging.getLogger("big-flavor-mcp")


@register
class RemoveArtifacts(AudioTool):
    name = "remove_artifacts"
    summary = "Detect and remove clicks, pops, and digital glitches."
    description = "Detect and remove clicks, pops, and digital glitches from audio"
    takes_region = True
    takes_strength = True
    params = [
        Param("sensitivity", float, default=0.5, minimum=0, maximum=1,
              label="Detection sensitivity", help="Detection sensitivity 0-1"),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Count clicks and pops without repairing them."""
        try:
            y, sr, _offset_s, _duration = load_for_analysis(file_path, start_s, end_s)
            measured = detect_clicks(y, sr)
            recommended = measured["count"] > 0
            return {
                "status": "success",
                "tool": self.name,
                "recommended": recommended,
                # Not the declared 0.5: that cuts at the 90th-percentile jump,
                # so apply() would interpolate a tenth of the file to repair
                # three clicks. This is as close to the measurement as the param
                # can get — and usually that is its floor,
                # CLICK_MIN_SENSITIVITY, which still means the top 0.1% of the
                # file's jumps rather than the counted events. `sensitivity` is
                # a percentile of every file by construction; a card targeting
                # the measured clicks alone needs apply() to take positions, not
                # a threshold (noted as a follow-up, deliberately not done here).
                "params": (
                    {"sensitivity": measured["recommended_sensitivity"]} if recommended else {}
                ),
                "findings": measured,
                # `worth=0` rather than a rate floor: the detector only fires on
                # a jump eight times the track's own loudest transient, so one
                # hit is already evidence — the rate only decides how loudly to
                # say so.
                "confidence": (
                    self.confidence_tier(measured["per_minute"], high=CLICK_HIGH_PER_MIN, worth=0.0)
                    if recommended else None
                ),
                "reason": (
                    f"{measured['count']} click{'' if measured['count'] == 1 else 's'} "
                    f"detected ({measured['per_minute']:.1f} per minute)"
                    if recommended else "No clicks or pops detected"
                ),
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing artifacts: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        sensitivity: float,
        output_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        strength: float = 1.0,
    ) -> dict:
        try:
            import numpy as np
            from scipy import signal

            # Load audio (channel count preserved; each channel is cleaned
            # independently)
            y, sr = _load_audio(file_path)

            kernel_size = int(sr * 0.001)  # 1ms kernel
            kernel = np.ones(kernel_size)
            window_size = int(sr * 0.0005)  # 0.5ms smoothing
            if window_size % 2 == 0:
                window_size += 1

            artifact_count = 0

            def clean_channel(ch: np.ndarray) -> np.ndarray:
                nonlocal artifact_count

                # Calculate first derivative to detect rapid changes
                derivative = np.diff(ch, prepend=ch[0])

                # Calculate threshold based on sensitivity
                threshold = np.percentile(np.abs(derivative), 100 - (sensitivity * 20))

                # Detect artifacts (rapid changes exceeding threshold)
                artifact_mask = np.abs(derivative) > threshold

                # Expand mask slightly to catch artifact tails
                artifact_mask_expanded = signal.convolve(
                    artifact_mask.astype(float),
                    kernel,
                    mode='same'
                ) > 0

                # Count artifacts
                artifact_count += int(np.sum(np.diff(artifact_mask_expanded.astype(int)) > 0))

                # Interpolate over artifacts
                ch_cleaned = ch.copy()
                artifact_indices = np.where(artifact_mask_expanded)[0]

                if len(artifact_indices) > 0:
                    # Group consecutive indices into regions
                    regions = []
                    start = artifact_indices[0]
                    for i in range(1, len(artifact_indices)):
                        if artifact_indices[i] != artifact_indices[i-1] + 1:
                            regions.append((start, artifact_indices[i-1]))
                            start = artifact_indices[i]
                    regions.append((start, artifact_indices[-1]))

                    # Interpolate each region
                    for start, end in regions:
                        if start > 0 and end < len(ch_cleaned) - 1:
                            # Linear interpolation
                            ch_cleaned[start:end+1] = np.linspace(
                                ch_cleaned[start-1],
                                ch_cleaned[end+1],
                                end - start + 1
                            )

                # Apply gentle smoothing
                return signal.savgol_filter(ch_cleaned, window_size, 3)

            # Clean the region (or the whole file when no region is given, a
            # byte-identical path) and wet/dry-blend it back per strength.
            def clean_process(segment: np.ndarray) -> np.ndarray:
                cleaned = _apply_per_channel(segment, clean_channel)
                return blend_strength(segment, cleaned, strength)

            y_cleaned, _ = apply_to_region(y, sr, start_s, end_s, clean_process)

            # Save output
            _write_audio(output_path, y_cleaned, sr)

            logger.info(f"Removed {artifact_count} artifacts")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "artifacts_removed": int(artifact_count),
                "sensitivity": sensitivity,
                "region": {"start_s": start_s, "end_s": end_s},
                "strength": strength
            }

        except Exception as e:
            logger.error(f"Error removing artifacts: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
