"""Region + strength helpers for the audio-cleanup toolchain (issue #65).

Every cleanup tool in ``big_flavor_mcp.py`` processes a whole file at a fixed
intensity. These helpers let a tool limit its effect to a time range and blend
between untouched and full effect, without each tool reimplementing the splicing
or the wet/dry math:

- :func:`resolve_region` turns an optional ``start_s``/``end_s`` pair into sample
  indices over librosa's ``(samples,)`` mono or ``(channels, samples)`` layout.
  Omitting both selects the whole signal, so the caller's existing whole-file
  path is byte-identical.
- :func:`apply_to_region` runs a per-region ``process_fn`` and splices the result
  back into the original with short equal-power crossfades at the boundaries, so
  the join has no click. It handles both length-preserving effects (EQ, noise
  reduction, hum, artifacts) and length-changing ones (time-stretch), reporting
  the processed region's new duration.
- :func:`blend_strength` is the wet/dry mix ``strength * processed +
  (1 - strength) * original`` used by the "how much" tools (noise reduction, EQ,
  hum removal, artifact removal). ``strength == 1`` reproduces today's output;
  ``strength == 0`` is a no-op.
"""

from typing import Callable, Optional, Tuple

import numpy as np


def _num_samples(y: np.ndarray) -> int:
    """Sample count regardless of mono ``(samples,)`` vs ``(channels, samples)``."""
    return y.shape[-1]


def resolve_region(
    y: np.ndarray,
    sr: int,
    start_s: Optional[float],
    end_s: Optional[float],
) -> Tuple[int, int]:
    """Resolve a time range to ``(start_sample, end_sample)`` (end exclusive).

    ``None`` for either bound extends to that edge of the signal, so
    ``resolve_region(y, sr, None, None)`` is the whole file. Bounds are clamped
    to the signal and ordered, so a caller can never index out of range.
    """
    n = _num_samples(y)
    start = 0 if start_s is None else int(round(start_s * sr))
    end = n if end_s is None else int(round(end_s * sr))
    start = max(0, min(start, n))
    end = max(0, min(end, n))
    if end < start:
        start, end = end, start
    return start, end


def _fade_ramps(length: int) -> Tuple[np.ndarray, np.ndarray]:
    """Equal-power fade-in/fade-out ramps of ``length`` samples.

    ``fade_in`` rises 0 -> 1, ``fade_out`` falls 1 -> 0, and ``fade_in ** 2 +
    fade_out ** 2 == 1`` at every sample so a crossfade holds constant power.
    """
    if length <= 0:
        return np.ones(0), np.ones(0)
    t = np.linspace(0.0, 1.0, length)
    fade_in = np.sin(t * np.pi / 2)
    fade_out = np.cos(t * np.pi / 2)
    return fade_in, fade_out


def fade_in_out(y: np.ndarray, sr: int, fade_ms: float) -> np.ndarray:
    """Apply an equal-power fade-in at the start and fade-out at the end of ``y``.

    Used at trim-to-selection cut points so a kept span opens and closes with a
    smooth ramp instead of a hard edge (a click). Works on mono ``(samples,)``
    and ``(channels, samples)`` layouts — the ramp broadcasts across channels.
    ``fade_ms`` is clamped so the two ramps never overlap; ``fade_ms <= 0``
    returns ``y`` unchanged. The input is not mutated (a copy is returned).
    """
    n = _num_samples(y)
    fade = int(round(fade_ms / 1000.0 * sr))
    fade = min(fade, n // 2)
    if fade <= 0:
        return y
    out = np.array(y, copy=True)
    fade_in, fade_out = _fade_ramps(fade)
    out[..., :fade] = out[..., :fade] * fade_in
    out[..., -fade:] = out[..., -fade:] * fade_out
    return out


def apply_to_region(
    y: np.ndarray,
    sr: int,
    start_s: Optional[float],
    end_s: Optional[float],
    process_fn: Callable[[np.ndarray], np.ndarray],
    crossfade_ms: float = 30.0,
) -> Tuple[np.ndarray, float]:
    """Run ``process_fn`` over a region and splice the result back in.

    With no region (``start_s is None and end_s is None``) this simply returns
    ``process_fn(y)`` unchanged — the whole-file path, no crossfade — so a caller
    that never sets a region is byte-identical to processing directly.

    With a region, only ``y[..., start:end]`` is passed to ``process_fn``. Audio
    outside the region is copied through **bit-identical**; the processed region
    is placed back in the gap; and a short equal-power crossfade (up to
    ``crossfade_ms``) is laid *over the region's own edges* — the region fades in
    over the original's tail at the leading boundary and out into the original's
    head at the trailing boundary — so the join has no click without deleting any
    samples. When ``process_fn`` returns a region of the same length (EQ, noise,
    hum, artifacts, pitch), the total length is unchanged; when it changes length
    (trim, time-stretch) the output length changes by the same amount.

    Returns ``(output, processed_region_seconds)`` — the processed region's
    duration after ``process_fn``, which a length-changing tool can report.
    """
    if start_s is None and end_s is None:
        processed_full = process_fn(y)
        return processed_full, _num_samples(processed_full) / sr

    start, end = resolve_region(y, sr, start_s, end_s)
    region = y[..., start:end]
    processed = np.array(process_fn(region), copy=True)
    processed_len = _num_samples(processed)

    before = y[..., :start]
    after = y[..., end:]

    # The crossfade blends the processed region's edge against the original
    # audio it abuts, over samples that belong to the processed region — so no
    # sample is dropped and the untouched sides stay bit-identical.
    fade = int(round(crossfade_ms / 1000.0 * sr))
    fade = min(fade, processed_len)

    if fade > 0:
        region_len = _num_samples(region)
        fade_in, fade_out = _fade_ramps(fade)
        # Leading edge: ramp from the original region's opening samples into the
        # processed opening samples (only if the region wasn't length-changed at
        # the front — i.e. the original had samples there to blend against).
        head_original = region[..., :fade] if region_len >= fade else None
        if head_original is not None and head_original.shape[-1] == fade:
            processed[..., :fade] = (
                head_original * fade_out + processed[..., :fade] * fade_in
            )
        # Trailing edge: ramp the processed tail out into the original region's
        # closing samples.
        tail_original = region[..., -fade:] if region_len >= fade else None
        if tail_original is not None and tail_original.shape[-1] == fade:
            processed[..., -fade:] = (
                processed[..., -fade:] * fade_out + tail_original * fade_in
            )

    output = np.concatenate([before, processed, after], axis=-1)
    return output, processed_len / sr


def blend_strength(
    original: np.ndarray,
    processed: np.ndarray,
    strength: float,
) -> np.ndarray:
    """Wet/dry blend: ``strength * processed + (1 - strength) * original``.

    ``strength == 1`` returns the processed signal (today's full effect),
    ``strength == 0`` returns the original untouched, and values between
    interpolate linearly. ``strength`` is clamped to ``[0, 1]``. The two signals
    are length-matched (trimmed to the shorter) so a tool whose DSP shifts the
    length by a few samples — e.g. an STFT round-trip — still blends cleanly.
    """
    strength = float(np.clip(strength, 0.0, 1.0))
    if strength >= 1.0:
        return processed
    if strength <= 0.0:
        return original[..., : _num_samples(processed)] if _num_samples(
            original
        ) != _num_samples(processed) else original
    length = min(_num_samples(original), _num_samples(processed))
    dry = original[..., :length]
    wet = processed[..., :length]
    return strength * wet + (1.0 - strength) * dry
