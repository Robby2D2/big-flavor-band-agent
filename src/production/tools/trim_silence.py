"""``trim_silence`` — remove head/tail silence, or keep only a chosen span."""

import logging
from typing import Optional

try:  # package import (tests: src.production.tools.trim_silence)
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _write_audio
    from ..region import apply_to_region, fade_in_out, resolve_region
    from ..analysis import load_for_analysis
except ImportError:  # flat sys.path (agent loads src/production directly)
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _write_audio
    from region import apply_to_region, fade_in_out, resolve_region
    from analysis import load_for_analysis

logger = logging.getLogger("big-flavor-mcp")


@register
class TrimSilence(AudioTool):
    name = "trim_silence"
    summary = "Trim non-musical content (silence) from the head and tail."
    description = (
        "Remove silence from the beginning and end of audio. Perfect for "
        "cleaning up raw recordings."
    )
    takes_region = True
    params = [
        Param("threshold_db", float, default=-40, minimum=-80, maximum=0,
              label="Silence threshold (dB)",
              help="Audio quieter than this counts as silence to trim"),
        Param("trim_to_selection", bool, default=False, label="Keep only selection",
              help="When true, keep only the start_s..end_s span (discard everything "
                   "outside it) instead of trimming silence; requires start_s and/or end_s"),
        Param("fade_ms", float, default=10.0, minimum=0, maximum=200,
              label="Edge fade (ms)",
              help="Fade-in/out length applied at the cut points in trim-to-selection "
                   "mode, for a smooth edge instead of a click"),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Detect non-musical (silence/noise) content at the head and tail.

        Independent of the other tools: reports the detected music span (in
        absolute file time) and how much leading/trailing content trim would
        remove, so the UI can show it before committing.
        """
        try:
            import numpy as np
            import librosa

            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            if duration <= 0 or len(y) == 0:
                return {"status": "success", "tool": self.name, "recommended": False,
                        "params": {}, "findings": {}, "reason": "Empty selection",
                        "region": {"start_s": start_s, "end_s": end_s}}

            frame_length = int(sr * 0.1)
            hop_length = int(sr * 0.05)
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

            # Music has more consistent energy: low local RMS variance + energy.
            window_size = 20
            rms_std = np.array([np.std(rms[max(0, i - window_size):i + window_size])
                                for i in range(len(rms))])
            music_threshold = np.percentile(rms_std, 30)
            is_music = (rms_std < music_threshold) & (rms > np.percentile(rms, 10))
            music_indices = np.where(is_music)[0]

            if len(music_indices) > 0:
                music_start = music_indices[0] * hop_length / sr
                music_end = music_indices[-1] * hop_length / sr
                trim_from_start = max(0.0, music_start - 0.1)
                trim_from_end = max(0.0, duration - music_end - 0.1)
            else:
                music_start, music_end = 0.0, duration
                trim_from_start = trim_from_end = 0.0

            recommended = bool(trim_from_start > 0.5 or trim_from_end > 0.5)
            return {
                "status": "success",
                "tool": self.name,
                "recommended": recommended,
                "params": {},  # threshold_db stays the user's choice
                "findings": {
                    "detected_music_start": round(float(music_start) + offset_s, 2),
                    "detected_music_end": round(float(music_end) + offset_s, 2),
                    "trim_start_seconds": round(float(trim_from_start), 2),
                    "trim_end_seconds": round(float(trim_from_end), 2),
                },
                "reason": (
                    f"Found {trim_from_start:.1f}s of non-musical content at the start "
                    f"and {trim_from_end:.1f}s at the end"
                    if recommended else "No significant non-musical content at the edges"
                ),
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing trim: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        threshold_db: float,
        output_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        trim_to_selection: bool = False,
        fade_ms: float = 10.0,
    ) -> dict:
        try:
            import librosa
            import numpy as np

            # Load audio (channel count preserved)
            y, sr = _load_audio(file_path)
            original_duration = y.shape[-1] / sr

            if trim_to_selection:
                # Keep only the chosen span, with fades at the cut points.
                if start_s is None and end_s is None:
                    return {
                        "status": "error",
                        "error": "trim_to_selection requires start_s and/or end_s",
                        "input_file": file_path
                    }
                sel_start, sel_end = resolve_region(y, sr, start_s, end_s)
                if sel_end <= sel_start:
                    return {
                        "status": "error",
                        "error": "Selected trim region is empty",
                        "input_file": file_path
                    }
                y_trimmed = np.array(y[..., sel_start:sel_end], copy=True)
                y_trimmed = fade_in_out(y_trimmed, sr, fade_ms)
            else:
                def trim_process(segment: np.ndarray) -> np.ndarray:
                    # Find non-silent intervals on the mono mix so both channels
                    # share the same trim points
                    non_silent = librosa.effects.split(_to_mono(segment), top_db=-threshold_db)
                    if len(non_silent) == 0:
                        raise ValueError("No non-silent audio found")
                    start_sample = non_silent[0][0]
                    end_sample = non_silent[-1][1]
                    return segment[..., start_sample:end_sample]

                # Trim within the region (or the whole file when no region is
                # given), keeping any audio outside the region intact.
                try:
                    y_trimmed, _ = apply_to_region(y, sr, start_s, end_s, trim_process)
                except ValueError as exc:
                    return {
                        "status": "error",
                        "error": str(exc),
                        "input_file": file_path
                    }

            trimmed_duration = y_trimmed.shape[-1] / sr

            # Save output
            _write_audio(output_path, y_trimmed, sr)

            logger.info(f"Trimmed silence: {original_duration:.2f}s → {trimmed_duration:.2f}s")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_duration_seconds": round(original_duration, 2),
                "trimmed_duration_seconds": round(trimmed_duration, 2),
                "removed_seconds": round(original_duration - trimmed_duration, 2),
                "threshold_db": threshold_db,
                "mode": "selection" if trim_to_selection else "silence",
                "fade_ms": fade_ms if trim_to_selection else None,
                "region": {"start_s": start_s, "end_s": end_s}
            }

        except Exception as e:
            logger.error(f"Error trimming silence: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
