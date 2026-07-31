"""``analyze_and_recommend_processing`` — whole-song "analyze everything" pass.

The bundled analyzer behind the produce editor's whole-song flow: one efficient
pass over the (optionally region-scoped) audio that reports issues + recommended
settings for every cleanup step at once (trim / noise / hum / eq / compression /
normalization / mastering). Distinct from the per-tool ``analyze()`` methods
(which each inspect one concern on demand) — this is the "scan the whole thing"
entry the auto-clean orchestrator and the editor's recommendation panel use.
"""

import logging
from typing import Optional

try:
    from ..toolkit import AudioTool, register
    from ..region import resolve_region
    from ..analysis import detect_hum, measure_integrated_lufs
except ImportError:
    from toolkit import AudioTool, register
    from region import resolve_region
    from analysis import detect_hum, measure_integrated_lufs

logger = logging.getLogger("big-flavor-mcp")


def _generate_analysis_summary(recommendations: dict) -> str:
    """Generate human-readable summary of analysis."""
    issues = []

    if recommendations["trim"]["recommended"]:
        trim_start = recommendations["trim"]["trim_start_seconds"]
        trim_end = recommendations["trim"]["trim_end_seconds"]
        issues.append(f"Found {trim_start:.1f}s of noise/speech at start, {trim_end:.1f}s at end")

    if recommendations["noise_reduction"]["recommended"]:
        noise_db = recommendations["noise_reduction"]["noise_level_db"]
        issues.append(f"Background noise at {noise_db:.1f} dB")

    if recommendations["hum"]["recommended"]:
        fundamental = recommendations["hum"]["fundamental_hz"]
        harmonic_count = len(recommendations["hum"]["harmonics_affected"])
        issues.append(
            f"Mains hum at {fundamental:.0f} Hz ({harmonic_count} affected frequencies)"
        )

    if recommendations["eq"]["recommended"]:
        issues.append(f"{len(recommendations['eq']['adjustments'])} frequency imbalances detected")

    if recommendations["warnings"]:
        issues.extend(recommendations["warnings"])

    if not issues:
        return "Audio is in good condition, only standard mastering recommended"

    return "; ".join(issues)


@register
class AnalyzeRecommend(AudioTool):
    name = "analyze_and_recommend_processing"
    summary = "Analyze the whole song and recommend a cleanup workflow."
    description = (
        "Analyze audio and recommend optimal processing settings. Detects issues "
        "like noise, clipping, frequency imbalance, and suggests the best cleanup "
        "workflow with specific parameters."
    )
    takes_output = False
    takes_region = True
    hidden_from_editor = True  # whole-song scan, not a single-effect editor tool
    params = []

    async def apply(
        self,
        ctx,
        file_path: str,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
    ) -> dict:
        try:
            import librosa
            import numpy as np
            from scipy import signal, stats

            logger.info(f"Performing comprehensive analysis on: {file_path}")

            # Load audio
            y_full, sr = librosa.load(file_path, sr=None)

            # Scope analysis to the requested span; absolute-time fields are
            # restored when the recommendations are compiled.
            region_start_sample, region_end_sample = resolve_region(y_full, sr, start_s, end_s)
            region_offset_s = region_start_sample / sr
            y = y_full[region_start_sample:region_end_sample]
            duration = len(y) / sr

            # ===== 1. ANALYZE LEADING/TRAILING CONTENT =====
            frame_length = int(sr * 0.1)  # 100ms frames
            hop_length = int(sr * 0.05)   # 50ms hops

            rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]

            spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]
            spectral_rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=hop_length)[0]
            zcr = librosa.feature.zero_crossing_rate(y, frame_length=frame_length, hop_length=hop_length)[0]

            window_size = 20  # ~1 second windows
            rms_std = np.array([np.std(rms[max(0, i - window_size):i + window_size])
                                for i in range(len(rms))])

            music_threshold = np.percentile(rms_std, 30)
            is_music = rms_std < music_threshold
            is_music = is_music & (rms > np.percentile(rms, 10))

            music_indices = np.where(is_music)[0]
            if len(music_indices) > 0:
                music_start_frame = music_indices[0]
                music_end_frame = music_indices[-1]
                trim_start_time = music_start_frame * hop_length / sr
                trim_end_time = (music_end_frame * hop_length / sr)
                trim_from_start = max(0, trim_start_time - 0.1)
                trim_from_end = max(0, duration - trim_end_time - 0.1)
            else:
                trim_from_start = 0
                trim_from_end = 0
                trim_start_time = 0
                trim_end_time = duration

            # ===== 2. ANALYZE NOISE FLOOR =====
            quiet_threshold = np.percentile(rms, 20)
            quiet_sections = rms < quiet_threshold
            quiet_samples = y[np.repeat(quiet_sections, hop_length)[:len(y)]]

            if len(quiet_samples) > sr:
                noise_level = np.sqrt(np.mean(quiet_samples**2))
                noise_level_db = 20 * np.log10(noise_level + 1e-10)
                if noise_level_db > -40:
                    recommended_noise_reduction = 0.8
                elif noise_level_db > -50:
                    recommended_noise_reduction = 0.6
                else:
                    recommended_noise_reduction = 0.4
            else:
                noise_level_db = -60.0
                recommended_noise_reduction = 0.5

            # ===== 2b. DETECT MAINS HUM =====
            hum = detect_hum(y, sr)

            # ===== 3. ANALYZE FREQUENCY BALANCE =====
            D = np.abs(librosa.stft(y))
            avg_spectrum = np.mean(D, axis=1)
            freqs = librosa.fft_frequencies(sr=sr)

            bass_band = (freqs >= 20) & (freqs < 250)
            mid_band = (freqs >= 250) & (freqs < 2000)
            treble_band = (freqs >= 2000) & (freqs < 8000)

            bass_energy = np.mean(avg_spectrum[bass_band])
            mid_energy = np.mean(avg_spectrum[mid_band])
            treble_energy = np.mean(avg_spectrum[treble_band])

            total_energy = bass_energy + mid_energy + treble_energy
            bass_pct = 100 * bass_energy / total_energy
            mid_pct = 100 * mid_energy / total_energy
            treble_pct = 100 * treble_energy / total_energy

            eq_recommendations = []

            sub_bass = (freqs >= 20) & (freqs < 60)
            sub_bass_energy = np.mean(avg_spectrum[sub_bass])
            if sub_bass_energy > bass_energy * 0.3:
                eq_recommendations.append({
                    "type": "high_pass", "frequency": 80,
                    "reason": "Excessive low-frequency rumble detected"
                })
            elif sub_bass_energy > bass_energy * 0.2:
                eq_recommendations.append({
                    "type": "high_pass", "frequency": 60,
                    "reason": "Some low-frequency rumble present"
                })

            if bass_pct > 45:
                eq_recommendations.append({
                    "type": "reduce", "frequency": 200, "amount": -3,
                    "reason": "Bass-heavy mix, may sound muddy"
                })

            if treble_pct < 15:
                eq_recommendations.append({
                    "type": "boost", "frequency": 4000, "amount": 2,
                    "reason": "Lacks high-frequency clarity"
                })
            elif treble_pct > 35:
                eq_recommendations.append({
                    "type": "low_pass", "frequency": 12000,
                    "reason": "Excessive high-frequency content (may be harsh)"
                })

            # ===== 4. ANALYZE DYNAMIC RANGE =====
            peak = np.max(np.abs(y))
            rms_overall = np.sqrt(np.mean(y**2))
            crest_factor = peak / (rms_overall + 1e-10)
            crest_factor_db = 20 * np.log10(crest_factor)

            clipping_threshold = 0.99
            clipped_samples = np.sum(np.abs(y) > clipping_threshold)
            clipping_pct = 100 * clipped_samples / len(y)

            if crest_factor_db > 18:
                recommended_compression = "aggressive"
                compression_ratio = 4.0
            elif crest_factor_db > 14:
                recommended_compression = "moderate"
                compression_ratio = 3.0
            else:
                recommended_compression = "gentle"
                compression_ratio = 2.0

            # ===== 5. ANALYZE LOUDNESS =====
            peak_db = 20 * np.log10(peak) if peak > 0 else -np.inf
            rms_db = 20 * np.log10(rms_overall) if rms_overall > 0 else -np.inf

            estimated_lufs = measure_integrated_lufs(y, sr)

            if estimated_lufs < -30:
                recommended_lufs = -14
                recommended_gain = estimated_lufs + 14
            elif estimated_lufs < -20:
                recommended_lufs = -14
                recommended_gain = estimated_lufs + 14
            else:
                recommended_lufs = -14
                recommended_gain = min(estimated_lufs + 14, 12)

            eq_intensity = (
                "gentle" if len(eq_recommendations) <= 1
                else "moderate" if len(eq_recommendations) == 2
                else "aggressive"
            )
            mastering_gain_abs = abs(float(recommended_gain))
            mastering_intensity = (
                "gentle" if mastering_gain_abs < 4
                else "moderate" if mastering_gain_abs < 8
                else "aggressive"
            )

            recommendations = {
                "trim": {
                    "recommended": bool(trim_from_start > 0.5 or trim_from_end > 0.5),
                    "trim_start_seconds": round(float(trim_from_start), 2),
                    "trim_end_seconds": round(float(trim_from_end), 2),
                    "detected_music_start": round(float(trim_start_time) + region_offset_s, 2),
                    "detected_music_end": round(float(trim_end_time) + region_offset_s, 2),
                    "reason": "Non-musical content detected before/after main audio"
                },
                "noise_reduction": {
                    "recommended": bool(noise_level_db > -55),
                    "noise_level_db": round(float(noise_level_db), 1),
                    "recommended_strength": float(recommended_noise_reduction),
                    "recommended_profile_duration": 1.0,
                    "recommended_intensity": (
                        "aggressive" if recommended_noise_reduction >= 0.8
                        else "moderate" if recommended_noise_reduction >= 0.6
                        else "gentle"
                    ),
                    "reason": f"Background noise at {noise_level_db:.1f} dB"
                },
                "hum": {
                    "recommended": hum["detected"],
                    "fundamental_hz": hum["fundamental_hz"],
                    "harmonics_affected": hum["harmonics_affected"],
                    "prominence_db": hum["prominence_db"],
                    "reason": (
                        f"Mains hum detected at {hum['fundamental_hz']:.0f} Hz "
                        f"({len(hum['harmonics_affected'])} affected frequencies)"
                        if hum["detected"] else "No mains hum detected"
                    )
                },
                "eq": {
                    "recommended": len(eq_recommendations) > 0,
                    "adjustments": eq_recommendations,
                    "recommended_intensity": eq_intensity,
                    "frequency_balance": {
                        "bass_percent": round(float(bass_pct), 1),
                        "mid_percent": round(float(mid_pct), 1),
                        "treble_percent": round(float(treble_pct), 1)
                    }
                },
                "compression": {
                    "recommended": True,
                    "level": recommended_compression,
                    "ratio": float(compression_ratio),
                    "crest_factor_db": round(float(crest_factor_db), 1),
                    "reason": f"Dynamic range: {crest_factor_db:.1f} dB"
                },
                "normalization": {
                    "recommended": bool(peak_db < -6 or peak_db > -1),
                    "current_peak_db": round(float(peak_db), 1),
                    "target_peak_db": -3.0,
                    "recommended_intensity": recommended_compression,
                    "reason": "Level optimization needed"
                },
                "mastering": {
                    "recommended": True,
                    "current_lufs_measured": round(float(estimated_lufs), 1),
                    "target_lufs": float(recommended_lufs),
                    "estimated_gain_db": round(float(recommended_gain), 1),
                    "recommended_intensity": mastering_intensity
                },
                "warnings": []
            }

            if clipping_pct > 0.1:
                recommendations["warnings"].append(
                    f"Clipping detected: {clipping_pct:.2f}% of samples are clipped"
                )

            if estimated_lufs > -10:
                recommendations["warnings"].append(
                    "Audio is very loud and may be over-compressed"
                )

            logger.info(f"Analysis complete. {len(recommendations)} categories analyzed")

            return {
                "status": "success",
                "file_path": file_path,
                "duration_seconds": round(float(duration), 2),
                "sample_rate": int(sr),
                "detected_music_start": recommendations["trim"]["detected_music_start"],
                "detected_music_end": recommendations["trim"]["detected_music_end"],
                "region": {"start_s": start_s, "end_s": end_s},
                "recommendations": recommendations,
                "processing_order": [
                    "1. Trim non-musical content" if recommendations["trim"]["recommended"] else None,
                    "2. Remove mains hum" if recommendations["hum"]["recommended"] else None,
                    "3. Reduce noise" if recommendations["noise_reduction"]["recommended"] else None,
                    "4. Apply EQ corrections" if recommendations["eq"]["recommended"] else None,
                    "5. Normalize with compression",
                    "6. Apply mastering"
                ],
                "summary": _generate_analysis_summary(recommendations)
            }

        except Exception as e:
            logger.error(f"Error analyzing audio: {e}")
            return {
                "status": "error",
                "error": str(e),
                "file_path": file_path
            }
