"""``reduce_noise`` — spectral-gating background-noise removal."""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register
    from ..audio_io import _load_audio, _write_audio
    from ..region import apply_to_region, blend_strength, resolve_region
    from ..analysis import load_for_analysis
except ImportError:
    from toolkit import AudioTool, Param, register
    from audio_io import _load_audio, _write_audio
    from region import apply_to_region, blend_strength, resolve_region
    from analysis import load_for_analysis

logger = logging.getLogger("big-flavor-mcp")


@register
class ReduceNoise(AudioTool):
    name = "reduce_noise"
    summary = "Remove background noise, hiss, and feedback."
    description = "Remove background noise, hum, hiss, and feedback from audio recordings"
    takes_region = True
    takes_strength = True
    params = [
        Param("noise_profile_duration", float, default=1.0, minimum=0.1, maximum=10,
              label="Noise profile duration (s)",
              help="Amount of the quietest audio (seconds) used to estimate the noise profile"),
        Param("reduction_strength", float, default=0.7, minimum=0, maximum=1,
              label="Reduction strength",
              help="Noise reduction strength 0-1 (scales the spectral gate itself)"),
        Param("highpass_hz", float, label="High-pass (Hz)",
              help="Optional high-pass cutoff in Hz to remove low-frequency rumble "
                   "(default: off; use the EQ tool for rumble control)"),
        Param("noise_start_s", float, label="Noise patch start (s)",
              help="Optional start of a clean pure-noise patch to sample as the noise "
                   "profile, instead of the quietest frames of the processed audio"),
        Param("noise_end_s", float, label="Noise patch end (s)",
              help="Optional end of the noise-profile patch"),
        Param("non_stationary", bool, default=False, label="Adaptive (non-stationary)",
              help="Use an adaptive time-varying noise estimate that can remove "
                   "intermittent noise (talking, a door, a thump) a fixed profile can't"),
    ]

    async def analyze(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        **params,
    ) -> dict:
        """Measure the noise floor and recommend a reduction strength."""
        try:
            import numpy as np
            import librosa

            y, sr, offset_s, duration = load_for_analysis(file_path, start_s, end_s)
            if len(y) == 0:
                return {"status": "success", "tool": self.name, "recommended": False,
                        "params": {}, "findings": {}, "reason": "Empty selection",
                        "region": {"start_s": start_s, "end_s": end_s}}

            hop_length = int(sr * 0.05)
            frame_length = int(sr * 0.1)
            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
            quiet_threshold = np.percentile(rms, 20)
            quiet_sections = rms < quiet_threshold
            quiet_samples = y[np.repeat(quiet_sections, hop_length)[:len(y)]]

            if len(quiet_samples) > sr:
                noise_level = np.sqrt(np.mean(quiet_samples ** 2))
                noise_level_db = 20 * np.log10(noise_level + 1e-10)
                if noise_level_db > -40:
                    recommended_strength = 0.8
                elif noise_level_db > -50:
                    recommended_strength = 0.6
                else:
                    recommended_strength = 0.4
            else:
                noise_level_db = -60.0
                recommended_strength = 0.5

            recommended = bool(noise_level_db > -55)
            return {
                "status": "success",
                "tool": self.name,
                "recommended": recommended,
                "params": {"reduction_strength": float(recommended_strength),
                           "noise_profile_duration": 1.0},
                "findings": {"noise_level_db": round(float(noise_level_db), 1)},
                "reason": f"Background noise floor at {noise_level_db:.1f} dB",
                "region": {"start_s": start_s, "end_s": end_s},
            }
        except Exception as e:
            logger.error(f"Error analyzing noise: {e}")
            return {"status": "error", "tool": self.name, "error": str(e)}

    async def apply(
        self,
        ctx,
        file_path: str,
        noise_profile_duration: float,
        reduction_strength: float,
        output_path: str,
        highpass_hz: Optional[float] = None,
        subtype: Optional[str] = None,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
        strength: float = 1.0,
        noise_start_s: Optional[float] = None,
        noise_end_s: Optional[float] = None,
        non_stationary: bool = False,
    ) -> dict:
        try:
            import librosa
            import numpy as np
            from scipy import signal
            from scipy.ndimage import median_filter

            # Load audio (channel count preserved; each channel is denoised
            # independently with its own noise profile)
            y, sr = _load_audio(file_path)
            hop_length = 512  # librosa.stft default
            channel_stats = []  # (original_noise, reduced_noise) per channel

            # Optional explicit noise-profile clip, sampled from absolute file
            # coordinates so the caller can point at pure noise anywhere in the
            # file rather than relying on the quietest frames of the processed
            # region (issue #66).
            noise_clip = None
            if noise_start_s is not None or noise_end_s is not None:
                ns, ne = resolve_region(y, sr, noise_start_s, noise_end_s)
                if ne > ns:
                    noise_clip = y[..., ns:ne]

            def quietest_frame_rms(ch: np.ndarray) -> float:
                """Mean RMS of the quietest frames — the residual noise metric."""
                mag = np.abs(librosa.stft(ch))
                frame_rms = np.sqrt((mag ** 2).mean(axis=0))
                n = int(round(noise_profile_duration * sr / hop_length))
                n = max(1, min(n, mag.shape[1]))
                return float(np.sort(frame_rms)[:n].mean())

            def denoise_channel(ch: np.ndarray, ch_noise: Optional[np.ndarray]) -> np.ndarray:
                if non_stationary:
                    # Adaptive, time-varying noise estimate (issue #66). Removes
                    # intermittent noise a single fixed profile can't.
                    import noisereduce as nr
                    before = quietest_frame_rms(ch)
                    prop = float(np.clip(reduction_strength, 0.0, 1.0))
                    ch_denoised = nr.reduce_noise(
                        y=ch, sr=sr, stationary=False, prop_decrease=prop,
                        y_noise=ch_noise if ch_noise is not None and ch_noise.shape[-1] > 0 else None
                    ).astype(ch.dtype, copy=False)
                    if highpass_hz:
                        sos = signal.butter(4, highpass_hz, 'hp', fs=sr, output='sos')
                        ch_denoised = signal.sosfilt(sos, ch_denoised)
                    channel_stats.append((before, quietest_frame_rms(ch_denoised)))
                    return ch_denoised

                n_samples = ch.shape[-1]

                # Compute STFT
                D = librosa.stft(ch)
                mag = np.abs(D)
                phase = np.angle(D)

                # Estimate the noise spectrum. By default use the quietest frames
                # of the whole channel rather than its opening seconds: in the
                # auto-clean chain the input is already trimmed to music start,
                # so "the beginning" is music, not noise (issue #56). When the
                # caller supplies an explicit noise clip, sample the profile from
                # that instead (issue #66).
                frame_rms = np.sqrt((mag ** 2).mean(axis=0))
                n_noise_frames = int(round(noise_profile_duration * sr / hop_length))
                n_noise_frames = max(1, min(n_noise_frames, mag.shape[1]))
                quietest_frames = np.argsort(frame_rms)[:n_noise_frames]
                if ch_noise is not None and ch_noise.shape[-1] > 0:
                    noise_mag = np.abs(librosa.stft(ch_noise)).mean(axis=1, keepdims=True)
                else:
                    noise_mag = mag[:, quietest_frames].mean(axis=1, keepdims=True)

                # Spectral gating: reduce magnitude where it's close to noise level
                # Scale noise threshold by reduction strength
                noise_threshold = noise_mag * (2 - reduction_strength)

                # Apply soft gating, then smooth the mask across frequency and
                # time so isolated bins don't flip open/closed frame-to-frame
                # (the source of watery "musical noise" artifacts).
                mask = np.maximum(0, 1 - (noise_threshold / (mag + 1e-10)))
                mask = median_filter(mask, size=(3, 5))
                mag_reduced = mag * mask

                # Reconstruct signal at the original channel length
                D_reduced = mag_reduced * np.exp(1j * phase)
                ch_denoised = librosa.istft(D_reduced, length=n_samples)

                if highpass_hz:
                    sos = signal.butter(4, highpass_hz, 'hp', fs=sr, output='sos')
                    ch_denoised = signal.sosfilt(sos, ch_denoised)

                # Noise floor before vs after, measured on the quietest frames
                rms_after = np.sqrt((np.abs(librosa.stft(ch_denoised)) ** 2).mean(axis=0))
                channel_stats.append((
                    float(frame_rms[quietest_frames].mean()),
                    float(rms_after[quietest_frames].mean())
                ))

                return ch_denoised

            # Denoise the region (or the whole file when no region is given, a
            # byte-identical path) and wet/dry-blend it back per strength. The
            # per-channel loop threads each channel's matching slice of the
            # explicit noise clip (when one was given) so stereo channels keep
            # independent profiles.
            def denoise_process(segment: np.ndarray) -> np.ndarray:
                if segment.ndim == 1:
                    ch_noise = noise_clip if noise_clip is not None else None
                    denoised = denoise_channel(segment, ch_noise)
                else:
                    results = []
                    for ci in range(segment.shape[0]):
                        if noise_clip is None:
                            ch_noise = None
                        elif noise_clip.ndim > 1:
                            ch_noise = noise_clip[ci]
                        else:
                            ch_noise = noise_clip
                        results.append(denoise_channel(segment[ci], ch_noise))
                    min_len = min(r.shape[-1] for r in results)
                    denoised = np.vstack([r[..., :min_len] for r in results])
                return blend_strength(segment, denoised, strength)

            y_filtered, _ = apply_to_region(y, sr, start_s, end_s, denoise_process)

            # Save output
            _write_audio(output_path, y_filtered, sr, subtype=subtype)

            original_noise = float(np.mean([s[0] for s in channel_stats]))
            reduced_noise = float(np.mean([s[1] for s in channel_stats]))
            noise_reduction_db = 20 * np.log10(original_noise / (reduced_noise + 1e-10))

            logger.info(f"Noise reduction applied: {noise_reduction_db:.1f} dB reduction")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "reduction_strength": reduction_strength,
                "noise_reduction_db": round(float(noise_reduction_db), 1),
                "noise_profile_duration": noise_profile_duration,
                "highpass_hz": highpass_hz,
                "region": {"start_s": start_s, "end_s": end_s},
                "noise_profile_region": {"start_s": noise_start_s, "end_s": noise_end_s},
                "non_stationary": non_stationary,
                "strength": strength
            }

        except Exception as e:
            logger.error(f"Error reducing noise: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
