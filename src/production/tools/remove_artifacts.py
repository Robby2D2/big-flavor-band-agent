"""``remove_artifacts`` — detect and interpolate clicks/pops/glitches."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _apply_per_channel, _write_audio
    from ..region import apply_to_region, blend_strength
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _apply_per_channel, _write_audio
    from region import apply_to_region, blend_strength

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
