"""``create_transition`` — beat-matched DJ crossfade between two songs."""

import logging
from pathlib import Path

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio

logger = logging.getLogger("big-flavor-mcp")


@register
class CreateTransition(AudioTool):
    name = "create_transition"
    summary = "Create a beat-matched DJ transition between two songs."
    description = "Create a beat-matched DJ transition between two songs"
    takes_file = False  # takes two input files, declared explicitly below
    params = [
        Param("song1_path", str, required=True, label="First song",
              help="Path to the first song"),
        Param("song2_path", str, required=True, label="Second song",
              help="Path to the second song"),
        Param("transition_duration", float, default=8, minimum=1, maximum=60,
              label="Transition duration (s)", help="Duration of transition in seconds"),
    ]

    async def apply(
        self,
        ctx,
        song1_path: str,
        song2_path: str,
        transition_duration: float = 8,
        output_path: str = None,
    ) -> dict:
        try:
            import librosa
            import numpy as np

            # Load both songs (channel counts preserved)
            y1, sr1 = _load_audio(song1_path, sr=22050)
            y2, sr2 = _load_audio(song2_path, sr=22050)

            # Match channel counts: duplicate a mono song so a stereo partner
            # keeps its stereo image.
            if y1.ndim != y2.ndim:
                if y1.ndim == 1:
                    y1 = np.tile(y1, (y2.shape[0], 1))
                else:
                    y2 = np.tile(y2, (y1.shape[0], 1))

            # Resample if sample rates differ
            if sr1 != sr2:
                y2 = librosa.resample(y2, orig_sr=sr2, target_sr=sr1)
                sr = sr1
            else:
                sr = sr1

            # Detect tempos
            tempo1, beats1 = librosa.beat.beat_track(y=_to_mono(y1), sr=sr)
            tempo2, beats2 = librosa.beat.beat_track(y=_to_mono(y2), sr=sr)

            bpm1 = tempo1 if isinstance(tempo1, float) else tempo1[0]
            bpm2 = tempo2 if isinstance(tempo2, float) else tempo2[0]

            # Time-stretch song2 to match song1's tempo
            if abs(bpm1 - bpm2) > 1:
                stretch_ratio = bpm1 / bpm2
                y2 = _apply_per_channel(
                    y2, lambda ch: librosa.effects.time_stretch(ch, rate=stretch_ratio)
                )

            # Calculate transition length in samples
            transition_samples = int(transition_duration * sr)

            # Get ending of song1 and beginning of song2
            song1_end = y1[..., -transition_samples:]
            song2_start = y2[..., :transition_samples]

            # Create crossfade
            fade_out = np.linspace(1, 0, transition_samples)
            fade_in = np.linspace(0, 1, transition_samples)

            transition = song1_end * fade_out + song2_start * fade_in

            # Concatenate: song1 (minus transition) + transition + song2 (minus transition)
            output = np.concatenate([
                y1[..., :-transition_samples],
                transition,
                y2[..., transition_samples:]
            ], axis=-1)

            # Save output
            _write_audio(output_path, output, sr)

            logger.info(f"Created transition: {Path(song1_path).name} → {Path(song2_path).name}")

            return {
                "status": "success",
                "song1": song1_path,
                "song2": song2_path,
                "output_file": output_path,
                "transition_duration": transition_duration,
                "song1_bpm": round(bpm1, 1),
                "song2_bpm": round(bpm2, 1),
                "tempo_adjusted": abs(bpm1 - bpm2) > 1
            }

        except Exception as e:
            logger.error(f"Error creating transition: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
