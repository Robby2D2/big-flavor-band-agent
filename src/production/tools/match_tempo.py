"""``match_tempo`` — time-stretch the whole file to a target BPM (pitch kept)."""

import logging

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _to_mono, _apply_per_channel, _write_audio

logger = logging.getLogger("big-flavor-mcp")


@register
class MatchTempo(AudioTool):
    name = "match_tempo"
    summary = "Time-stretch audio to a target BPM without changing pitch."
    description = "Time-stretch audio to a specific BPM without changing pitch"
    params = [
        Param("target_bpm", float, required=True, minimum=20, maximum=300,
              label="Target BPM", help="Target tempo in BPM"),
    ]

    async def apply(self, ctx, file_path: str, target_bpm: float, output_path: str) -> dict:
        try:
            import librosa

            # Load audio (channel count preserved; analysis uses a mono mix)
            y, sr = _load_audio(file_path, sr=22050)

            # Detect current tempo
            tempo, _ = librosa.beat.beat_track(y=_to_mono(y), sr=sr)
            current_bpm = tempo if isinstance(tempo, float) else tempo[0]

            # Calculate stretch ratio
            stretch_ratio = target_bpm / current_bpm

            # Time-stretch audio
            y_stretched = _apply_per_channel(
                y, lambda ch: librosa.effects.time_stretch(ch, rate=stretch_ratio)
            )

            # Save output
            _write_audio(output_path, y_stretched, sr)

            logger.info(f"Tempo matched: {current_bpm:.1f} BPM → {target_bpm:.1f} BPM")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "original_bpm": round(current_bpm, 1),
                "target_bpm": target_bpm,
                "stretch_ratio": round(stretch_ratio, 3)
            }

        except Exception as e:
            logger.error(f"Error matching tempo: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
