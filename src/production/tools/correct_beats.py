"""``correct_beats`` — beat-level tempo correction toward a grid."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
    from ..analysis import (
        _detect_beats, _target_grid, _build_time_map, _apply_time_map,
        MIN_BEATS_FOR_GRID, LOW_BEAT_CONFIDENCE,
    )
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
    from analysis import (
        _detect_beats, _target_grid, _build_time_map, _apply_time_map,
        MIN_BEATS_FOR_GRID, LOW_BEAT_CONFIDENCE,
    )

logger = logging.getLogger("big-flavor-mcp")


@register
class CorrectBeats(AudioTool):
    name = "correct_beats"
    summary = "Beat-level tempo correction: nudge drifting beats toward a grid."
    description = (
        "Beat-level tempo correction: nudge detected beats toward a target grid "
        "to fix a section that locally rushes or drags, without robotizing the "
        "whole performance. Unlike match_tempo (which stretches the entire file "
        "to one BPM), this stretches each inter-beat segment independently at an "
        "adjustable strength. Detects beat times + a per-beat confidence and "
        "returns them, and computes a single time map that can be re-applied "
        "across a set of stems to keep them in sync. When beats are too sparse/"
        "low-confidence to form a reliable grid it says so instead of "
        "over-correcting."
    )
    params = [
        Param("strength", float, default=0.5, minimum=0, maximum=1,
              label="Correction strength",
              help="How far each beat is moved toward the grid, 0-1 "
                   "(0 = untouched, 1 = fully quantized)"),
        Param("target_bpm", float, label="Target BPM",
              help="Optional explicit target tempo (rigid grid). Omit to correct "
                   "toward a smoothed version of the performance's own tempo curve."),
        Param("time_map", dict, label="Shared time map",
              help="Optional pre-computed time map {src_times, dst_times} from a "
                   "previous correction of another stem in the same set, applied "
                   "verbatim so all stems stay in sync.",
              schema={
                  "type": "object",
                  "properties": {
                      "src_times": {"type": "array", "items": {"type": "number"}},
                      "dst_times": {"type": "array", "items": {"type": "number"}},
                  },
              }),
    ]

    async def analyze(self, ctx, file_path: str, **params) -> dict:
        """Detect beats + per-beat confidence; report whether a reliable grid exists."""
        try:
            import numpy as np

            y, sr = _load_audio(file_path)
            tempo_bpm, beat_times, beat_conf = _detect_beats(_to_mono(y), sr)
            mean_conf = float(np.mean(beat_conf)) if len(beat_conf) else 0.0
            reliable = len(beat_times) >= MIN_BEATS_FOR_GRID and mean_conf >= LOW_BEAT_CONFIDENCE
            return {
                "status": "success",
                "tool": self.name,
                "recommended": bool(reliable),
                "params": {},
                "findings": {
                    "detected_bpm": round(float(tempo_bpm), 1),
                    "beats_detected": int(len(beat_times)),
                    "mean_confidence": round(mean_conf, 3),
                    "reliable_grid": bool(reliable),
                },
                "reason": (
                    f"{len(beat_times)} beats at {tempo_bpm:.0f} BPM (confidence {mean_conf:.2f})"
                    if reliable else
                    "Beat grid too sparse/low-confidence to correct reliably"
                ),
            }
        except Exception as e:
            logger.error(f"Error analyzing beats: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        output_path: str,
        strength: float = 0.5,
        target_bpm: Optional[float] = None,
        time_map: Optional[dict] = None,
    ) -> dict:
        try:
            import numpy as np

            strength = float(min(1.0, max(0.0, strength)))

            # Load audio (channel count preserved; detection on the mono mix,
            # the same time map applied to every channel).
            y, sr = _load_audio(file_path)
            mono = _to_mono(y)

            # Shared-map path: apply a caller-supplied map verbatim so all stems
            # of a set stay locked together.
            if time_map is not None:
                src = np.asarray(time_map.get("src_times", []), dtype=float)
                dst = np.asarray(time_map.get("dst_times", []), dtype=float)
                if len(src) == 0 or len(src) != len(dst):
                    return {
                        "status": "error",
                        "error": "time_map must have equal-length src_times and dst_times",
                        "input_file": file_path,
                    }
                y_corrected = _apply_per_channel(
                    y, lambda ch: _apply_time_map(ch, sr, src, dst)
                )
                _write_audio(output_path, y_corrected, sr)
                logger.info(
                    f"correct_beats: applied shared time map ({len(src)} beats) to {file_path}"
                )
                return {
                    "status": "success",
                    "mode": "shared_time_map",
                    "input_file": file_path,
                    "output_file": output_path,
                    "beats_in_map": int(len(src)),
                    "time_map": {"src_times": src.tolist(), "dst_times": dst.tolist()},
                }

            tempo_bpm, beat_times, beat_conf = _detect_beats(mono, sr)

            # Reliability guard: too few beats to form a grid, or the detected
            # beats are uniformly weak (ambiguous pulse). Copy through unchanged
            # and say why rather than garbling the audio.
            mean_conf = float(np.mean(beat_conf)) if len(beat_conf) else 0.0
            if len(beat_times) < MIN_BEATS_FOR_GRID or mean_conf < LOW_BEAT_CONFIDENCE:
                _write_audio(output_path, y, sr)
                reason = (
                    f"Only {len(beat_times)} beats detected"
                    if len(beat_times) < MIN_BEATS_FOR_GRID
                    else f"Beat detection is low-confidence (mean {mean_conf:.2f})"
                )
                logger.info(f"correct_beats: {reason}; copied unchanged")
                return {
                    "status": "success",
                    "mode": "uncorrectable",
                    "input_file": file_path,
                    "output_file": output_path,
                    "reason": (
                        f"{reason}; no reliable beat grid could be formed. This "
                        "tool corrects a section drifting against a stable pulse; "
                        "it cannot fix ensemble members disagreeing within the "
                        "same beat (a performance issue). Audio copied unchanged."
                    ),
                    "detected_bpm": round(tempo_bpm, 1),
                    "beats": beat_times.tolist(),
                    "beat_confidence": [round(float(c), 3) for c in beat_conf],
                }

            grid_times = _target_grid(beat_times, target_bpm)
            src, dst = _build_time_map(beat_times, grid_times, strength)

            y_corrected = _apply_per_channel(
                y, lambda ch: _apply_time_map(ch, sr, src, dst)
            )
            _write_audio(output_path, y_corrected, sr)

            max_shift_ms = float(np.max(np.abs(dst - src)) * 1000) if len(src) else 0.0
            logger.info(
                f"correct_beats: {len(beat_times)} beats, {tempo_bpm:.1f} BPM, "
                f"strength={strength:.2f}, max shift {max_shift_ms:.0f} ms"
            )

            return {
                "status": "success",
                "mode": "beat_grid",
                "input_file": file_path,
                "output_file": output_path,
                "detected_bpm": round(tempo_bpm, 1),
                "strength": round(strength, 2),
                "target": "fixed_bpm" if target_bpm else "smoothed_tempo_curve",
                "target_bpm": float(target_bpm) if target_bpm else None,
                "beats_detected": int(len(beat_times)),
                "beats": beat_times.tolist(),
                "beat_confidence": [round(float(c), 3) for c in beat_conf],
                "max_shift_ms": round(max_shift_ms, 1),
                "time_map": {"src_times": src.tolist(), "dst_times": dst.tolist()},
                "note": (
                    "This corrects a section drifting against a stable pulse. It "
                    "cannot fix ensemble members disagreeing with each other "
                    "within the same beat (a performance issue) without artifacts; "
                    "keep strength conservative and preview before committing."
                ),
            }

        except Exception as e:
            logger.error(f"Error correcting beats: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path,
            }
