"""``remove_artifacts`` — find clicks/pops and rebuild just those samples.

Only the spans ``find_clicks`` flags are touched; every other sample comes out
bit-identical. It used to interpolate over a fixed top fraction of every file's
jumps and then Savitzky-Golay the whole channel — on a vocal that kept 1-7% of
the high end, a muffle on every file it ran over.
"""

import logging
from typing import Optional, Tuple

import numpy as np

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _apply_per_channel, _write_audio
    from ..region import apply_to_region, blend_strength
    from ..analysis import (
        detect_clicks, find_clicks, click_ratio, load_for_analysis, CLICK_HIGH_PER_MIN,
    )
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _apply_per_channel, _write_audio
    from region import apply_to_region, blend_strength
    from analysis import (
        detect_clicks, find_clicks, click_ratio, load_for_analysis, CLICK_HIGH_PER_MIN,
    )

logger = logging.getLogger("big-flavor-mcp")

# Samples rebuilt either side of a click's flagged jumps: its tail rings on a
# little past the step itself.
CLICK_MARGIN_MS = 0.5
# Longer than this is a burst or a dropout, not a click — left alone rather
# than guessed at.
CLICK_MAX_SPAN_MS = 20.0
# Linear-prediction order for the rebuild (~0.7 ms of history at 44.1 kHz).
AR_ORDER = 32


def _ar_coeffs(x: np.ndarray, order: int) -> np.ndarray:
    """Least-squares coefficients predicting ``x[n]`` from ``x[n-1] .. x[n-order]``."""
    rows = np.lib.stride_tricks.sliding_window_view(x, order)[:-1, ::-1]
    coeffs, *_ = np.linalg.lstsq(rows, x[order:], rcond=None)
    return coeffs


def _extrapolate(history: np.ndarray, coeffs: np.ndarray, n: int) -> np.ndarray:
    """Run the predictor ``n`` samples on from the end of ``history``."""
    order = len(coeffs)
    buf = np.concatenate([history[-order:], np.zeros(n)])
    for i in range(n):
        buf[order + i] = coeffs @ buf[i:order + i][::-1]
    return buf[order:]


def _rebuild_span(ch: np.ndarray, s: int, e: int) -> Optional[np.ndarray]:
    """Predict ``ch[s:e]`` from the audio either side of it.

    Forward from the left context and backward from the right, crossfaded
    across the gap, so the fill meets both edges. ``None`` when there is not
    enough context or the predictor ran away; the caller falls back to a
    straight line between the edges.
    """
    gap = e - s
    context = max(4 * AR_ORDER, 3 * gap)
    left = ch[max(0, s - context):s].astype(float)
    right = ch[e:e + context].astype(float)
    if len(left) < 2 * AR_ORDER or len(right) < 2 * AR_ORDER:
        return None
    forward = _extrapolate(left, _ar_coeffs(left, AR_ORDER), gap)
    backward_src = right[::-1]
    backward = _extrapolate(backward_src, _ar_coeffs(backward_src, AR_ORDER), gap)[::-1]
    w = 0.5 - 0.5 * np.cos(np.linspace(0.0, np.pi, gap))
    fill = forward * (1.0 - w) + backward * w
    limit = 2.0 * max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-6)
    if not np.all(np.isfinite(fill)) or np.max(np.abs(fill)) > limit:
        return None
    return fill


def repair_clicks(ch: np.ndarray, sr: int, ratio: float) -> Tuple[np.ndarray, int]:
    """Rebuild each click ``find_clicks`` flags at ``ratio``; return ``(out, count)``.

    A flagged jump ``i`` is the step ``ch[i] -> ch[i+1]``, so a click spanning
    jumps ``first .. last`` has corrupted ``ch[first+1 .. last]``; the margin
    widens that to take its ring-out too.
    """
    _jumps, _baseline, _flagged, spans = find_clicks(ch, sr, ratio)
    if not spans:
        return ch, 0
    out = np.array(ch, copy=True)
    margin = max(1, int(sr * CLICK_MARGIN_MS / 1000.0))
    max_span = int(sr * CLICK_MAX_SPAN_MS / 1000.0)
    repaired = 0
    for first, last in spans:
        s = max(1, first + 1 - margin)
        e = min(len(out) - 1, last + 1 + margin)
        if e <= s or e - s > max_span:
            continue
        fill = _rebuild_span(out, s, e)
        if fill is None:
            fill = np.linspace(out[s - 1], out[e], e - s + 2)[1:-1]
        out[s:e] = fill
        repaired += 1
    return out, repaired


@register
class RemoveArtifacts(AudioTool):
    name = "remove_artifacts"
    summary = "Detect and remove clicks, pops, and digital glitches."
    description = "Detect and remove clicks, pops, and digital glitches from audio"
    takes_region = True
    takes_strength = True
    params = [
        Param("sensitivity", float, default=0.5, minimum=0, maximum=1,
              label="Detection sensitivity",
              help="0-1: higher catches quieter clicks. 0.5 repairs exactly the clicks "
                   "the analysis counts; nothing else is touched"),
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
                # The sensitivity at which apply() repairs exactly the clicks
                # counted here, carried explicitly so the card says what it does.
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
            # Load audio (channel count preserved; each channel is cleaned
            # independently)
            y, sr = _load_audio(file_path)
            ratio = click_ratio(sensitivity)
            repaired = 0

            def clean_channel(ch):
                nonlocal repaired
                out, count = repair_clicks(ch, sr, ratio)
                repaired += count
                return out

            # Clean the region (or the whole file when no region is given, a
            # byte-identical path) and wet/dry-blend it back per strength.
            def clean_process(segment):
                cleaned = _apply_per_channel(segment, clean_channel)
                return blend_strength(segment, cleaned, strength)

            y_cleaned, _ = apply_to_region(y, sr, start_s, end_s, clean_process)

            # Save output
            _write_audio(output_path, y_cleaned, sr)

            logger.info(f"Repaired {repaired} clicks (ratio {ratio:.1f}x)")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "artifacts_removed": int(repaired),
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
