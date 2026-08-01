"""``correct_pitch`` — per-note key-aware auto-tune, or whole-file transpose."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
    from ..region import apply_to_region, resolve_region
    from ..analysis import (
        _segment_notes, _parse_key, _detect_key, _scale_midi_set, _snap_midi, _NOTE_NAMES,
    )
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
    from region import apply_to_region, resolve_region
    from analysis import (
        _segment_notes, _parse_key, _detect_key, _scale_midi_set, _snap_midi, _NOTE_NAMES,
    )

logger = logging.getLogger("big-flavor-mcp")


def _apply_global_shift(
    y, sr, semitones, file_path, output_path, auto_tune_enabled,
    start_s: Optional[float] = None, end_s: Optional[float] = None,
) -> dict:
    """Whole-file transposition by `semitones` (the legacy behaviour, used for
    manual mode and as the polyphonic auto-tune fallback).

    Honours an optional `start_s`/`end_s` region: the shift is applied only
    within the span and spliced back into the untouched remainder via the shared
    region helper (issue #65). Omitting both shifts the whole file."""
    import librosa

    def shift_process(segment):
        if abs(semitones) <= 0.01:
            return segment
        return _apply_per_channel(
            segment,
            lambda ch: librosa.effects.pitch_shift(ch, sr=sr, n_steps=semitones),
        )

    if abs(semitones) <= 0.01:
        logger.info("No pitch correction needed")

    y_corrected, _ = apply_to_region(y, sr, start_s, end_s, shift_process)
    _write_audio(output_path, y_corrected, sr)

    return {
        "status": "success",
        "input_file": file_path,
        "output_file": output_path,
        "semitones_shift": round(float(semitones), 2),
        "auto_tune_enabled": auto_tune_enabled,
        "region": {"start_s": start_s, "end_s": end_s},
    }


@register
class CorrectPitch(AudioTool):
    name = "correct_pitch"
    summary = "Fix wrong notes / tuning (per-note auto-tune or manual transpose)."
    description = (
        "Apply pitch correction to fix wrong notes or tuning issues. Auto-tune "
        "mode does per-note, key-aware correction on a monophonic source (solo "
        "vocal / lead line): it only nudges off-pitch notes toward the musical "
        "scale and leaves correct notes untouched. On polyphonic input it falls "
        "back to a whole-file shift and says so. Manual mode (auto_tune off) "
        "transposes the whole file by `semitones`."
    )
    takes_region = True
    params = [
        Param("semitones", float, default=0, minimum=-12, maximum=12,
              label="Semitones", help="Semitones to shift (positive or negative)"),
        Param("auto_tune", bool, default=False, label="Auto-tune",
              help="Enable automatic per-note pitch correction"),
        Param("correction_strength", float, default=1.0, minimum=0, maximum=1,
              label="Correction strength",
              help="Auto-tune only: how far each note is nudged toward its target pitch"),
        Param("key", str, label="Key",
              help="Auto-tune only: musical key to snap notes to, e.g. 'C', 'A minor'. "
                   "Omit to detect the key automatically."),
        Param("chromatic", bool, default=False, label="Chromatic",
              help="Auto-tune only: snap to the nearest semitone instead of the nearest "
                   "tone in the key/scale"),
    ]

    async def apply(
        self,
        ctx,
        file_path: str,
        semitones: float,
        auto_tune: bool,
        output_path: str,
        correction_strength: float = 1.0,
        key: Optional[str] = None,
        chromatic: bool = False,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
    ) -> dict:
        try:
            import librosa
            import numpy as np

            # Load audio (channel count preserved; pitch detection on mono mix).
            y_full, sr = _load_audio(file_path)

            if not auto_tune:
                return _apply_global_shift(
                    y_full, sr, semitones, file_path, output_path,
                    auto_tune_enabled=False, start_s=start_s, end_s=end_s,
                )

            region_start, region_end = resolve_region(y_full, sr, start_s, end_s)
            y = y_full[..., region_start:region_end]

            strength = float(min(1.0, max(0.0, correction_strength)))
            mono = _to_mono(y)

            # Probabilistic YIN: continuous f0 + per-frame voicing, far more
            # robust than piptrack peak-picking for a monophonic line.
            fmin = librosa.note_to_hz("C2")
            fmax = librosa.note_to_hz("C7")
            f0, voiced_flag, voiced_prob = librosa.pyin(
                mono, fmin=fmin, fmax=fmax, sr=sr
            )
            hop_length = 512  # librosa.pyin default

            voiced_ratio = float(np.mean(voiced_flag)) if len(voiced_flag) else 0.0
            # Mean pyin confidence over the frames it flagged as voiced. A clean
            # solo line sits high (~0.8+); a chord / full mix drags this down.
            voiced_conf = (
                float(np.mean(voiced_prob[voiced_flag])) if voiced_ratio > 0 else 0.0
            )

            # Polyphony / non-monophonic guard: a chord or full mix yields sparse
            # and/or low-confidence voicing. Rather than garble the audio, fall
            # back to the old whole-file shift and say so.
            if voiced_ratio < 0.25 or voiced_conf < 0.5:
                fallback = _apply_global_shift(
                    y_full, sr, semitones, file_path, output_path,
                    auto_tune_enabled=True, start_s=start_s, end_s=end_s,
                )
                fallback["mode"] = "global_fallback"
                fallback["fallback_reason"] = (
                    "Input does not look monophonic (voiced "
                    f"{voiced_ratio * 100:.0f}% of the time, mean confidence "
                    f"{voiced_conf:.2f}); note-level correction is unreliable, "
                    "applied a whole-file shift instead."
                )
                logger.info(
                    "correct_pitch: polyphonic/low-voicing input "
                    f"(ratio={voiced_ratio:.2f}, conf={voiced_conf:.2f}) → global fallback"
                )
                return fallback

            # Segment the f0 curve into discrete note events.
            notes = _segment_notes(f0, voiced_flag)
            if not notes:
                fallback = _apply_global_shift(
                    y_full, sr, semitones, file_path, output_path,
                    auto_tune_enabled=True, start_s=start_s, end_s=end_s,
                )
                fallback["mode"] = "global_fallback"
                fallback["fallback_reason"] = "No stable notes detected; applied a whole-file shift."
                return fallback

            # Determine the target scale.
            note_pitch_classes = [int(round(m)) % 12 for _, _, m in notes]
            parsed = _parse_key(key) if key else None
            if parsed is None:
                tonic_pc, is_minor = _detect_key(note_pitch_classes)
                key_source = "detected"
            else:
                tonic_pc, is_minor = parsed
                key_source = "supplied"
            scale_pcs = _scale_midi_set(tonic_pc, is_minor)
            key_name = f"{_NOTE_NAMES[tonic_pc]} {'minor' if is_minor else 'major'}"

            # Correct each note independently on the mono reference, then apply
            # the same per-note shift to every channel so stereo is preserved.
            def _correct_channel(channel):
                out = channel.copy()
                for start_f, end_f, note_midi in notes:
                    s = int(start_f * hop_length)
                    e = min(len(channel), int(end_f * hop_length))
                    if e <= s:
                        continue
                    target = _snap_midi(note_midi, chromatic, scale_pcs)
                    shift = (target - note_midi) * strength + semitones
                    if abs(shift) < 0.01:
                        continue
                    out[s:e] = librosa.effects.pitch_shift(
                        channel[s:e], sr=sr, n_steps=shift
                    )
                return out

            # Apply the per-note correction to the region, then splice it back
            # into the full signal with crossfaded boundaries via the shared
            # region helper. With no region this processes the whole file — the
            # byte-identical path.
            y_corrected, _ = apply_to_region(
                y_full, sr, start_s, end_s,
                lambda seg: _apply_per_channel(seg, _correct_channel),
            )
            _write_audio(output_path, y_corrected, sr)

            corrected = sum(
                1 for _, _, m in notes
                if abs((_snap_midi(m, chromatic, scale_pcs) - m) * strength + semitones) >= 0.01
            )
            logger.info(
                f"Auto-tune: {len(notes)} notes, key {key_name} ({key_source}), "
                f"{corrected} shifted, strength={strength:.2f}"
            )

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "auto_tune_enabled": True,
                "mode": "per_note",
                "notes_detected": len(notes),
                "notes_corrected": corrected,
                "key": key_name,
                "key_source": key_source,
                "chromatic": chromatic,
                "correction_strength": round(strength, 2),
                "region": {"start_s": start_s, "end_s": end_s},
            }

        except Exception as e:
            logger.error(f"Error correcting pitch: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
