"""``auto_clean_recording`` — whole-song cleanup pipeline over the registry.

Runs the bundled analysis, then chains the individual tools (trim → hum → noise
→ EQ → pitch → tempo → normalize → master) with float intermediates and a
single final 24-bit write. This is the registry *orchestrator*: it calls each
step's tool through ``REGISTRY`` rather than hard-coded methods, so the pipeline
and the single-effect tools can never drift. Region mode confines the per-region
steps to a span and skips whole-track steps (normalize/master/tempo).
"""

import logging
from pathlib import Path
from typing import Optional

try:
    from ..toolkit import AudioTool, Param, register, REGISTRY
    from ..audio_io import _load_audio, _write_audio, INTERMEDIATE_WAV_SUBTYPE, FINAL_WAV_SUBTYPE
    from ..region import resolve_region, fade_in_out
except ImportError:
    from toolkit import AudioTool, Param, register, REGISTRY
    from audio_io import _load_audio, _write_audio, INTERMEDIATE_WAV_SUBTYPE, FINAL_WAV_SUBTYPE
    from region import resolve_region, fade_in_out

logger = logging.getLogger("big-flavor-mcp")


@register
class AutoClean(AudioTool):
    name = "auto_clean_recording"
    summary = "One-click whole-song cleanup (analyze then chain every step)."
    description = (
        "Automatically analyze and clean a raw recording with intelligent "
        "parameter selection. Detects and removes leading/trailing noise (not "
        "just silence), applies optimal noise reduction, EQ, normalization, and "
        "mastering based on audio analysis."
    )
    takes_region = True
    hidden_from_editor = True  # a pipeline, not a single-effect editor tool
    params = [
        Param("aggressiveness", str, default="moderate",
              choices=["gentle", "moderate", "aggressive"], label="Aggressiveness",
              help="Global fallback intensity for any step/param not explicitly overridden"),
        Param("keep_intermediates", bool, default=False, label="Keep intermediates",
              help="Save intermediate processing steps for review"),
        Param("steps_override", dict, label="Steps override",
              help="Per-step on/off map keyed by trim/noise_reduction/eq/normalize/master",
              schema={"type": "object"}),
        Param("step_params", dict, label="Step params",
              help="Per-step raw-parameter overrides, e.g. {'master': {'target_lufs': -12}}",
              schema={"type": "object"}),
    ]

    async def apply(
        self,
        ctx,
        file_path: str,
        output_path: str,
        aggressiveness: str = "moderate",
        keep_intermediates: bool = False,
        steps_override: dict = None,
        step_params: Optional[dict] = None,
        start_s: Optional[float] = None,
        end_s: Optional[float] = None,
    ) -> dict:
        try:
            import numpy as np

            logger.info(f"Auto-cleaning recording: {file_path} (aggressiveness: {aggressiveness})")

            has_region = start_s is not None or end_s is not None

            # Step 1: Analyze (scoped to the region when set).
            analysis = await REGISTRY["analyze_and_recommend_processing"].apply(
                ctx, file_path, start_s=start_s, end_s=end_s
            )
            if analysis.get("status") != "success":
                return analysis

            recommendations = analysis["recommendations"]

            overrides = steps_override or {}
            trim_override = overrides.get("trim")
            trim_selection = trim_override if isinstance(trim_override, dict) else None
            for _step in ("trim", "hum", "noise_reduction", "eq"):
                if _step in overrides:
                    recommendations[_step]["recommended"] = bool(overrides[_step])
            do_normalize = False if has_region else bool(overrides.get("normalize", True))
            do_master = False if has_region else bool(overrides.get("master", True))
            do_pitch = bool(overrides.get("pitch", False))
            do_tempo = False if has_region else bool(overrides.get("tempo", False))

            aggressiveness_multipliers = {"gentle": 0.7, "moderate": 1.0, "aggressive": 1.3}
            mult = aggressiveness_multipliers.get(aggressiveness, 1.0)

            sp = step_params or {}

            def step_param(step: str, param: str, default):
                return (sp.get(step) or {}).get(param, default)

            steps_taken = []
            current_file = file_path
            intermediate_dir = None

            if keep_intermediates:
                intermediate_dir = Path(output_path).parent / f"{Path(output_path).stem}_steps"
                intermediate_dir.mkdir(exist_ok=True)

            # Step 2: Trimming
            if recommendations["trim"]["recommended"]:
                logger.info("Step 1: Intelligent trimming...")
                if keep_intermediates:
                    trim_output = intermediate_dir / "01_trimmed.wav"
                else:
                    import tempfile
                    trim_output = Path(tempfile.mktemp(suffix=".wav"))

                if has_region:
                    threshold_db = step_param("trim", "threshold_db", -40.0)
                    result = await REGISTRY["trim_silence"].apply(
                        ctx, current_file, threshold_db, str(trim_output),
                        start_s=start_s, end_s=end_s
                    )
                    if result.get("status") == "success":
                        current_file = str(trim_output)
                        steps_taken.append({
                            "step": "trim",
                            "region": {"start_s": start_s, "end_s": end_s},
                            "removed_seconds": result.get("removed_seconds"),
                            "output": str(trim_output) if keep_intermediates else "temp"
                        })
                else:
                    y, sr = _load_audio(current_file)

                    if trim_selection and (
                        trim_selection.get("start_s") is not None
                        or trim_selection.get("end_s") is not None
                    ):
                        trim_start, trim_end = resolve_region(
                            y, sr, trim_selection.get("start_s"), trim_selection.get("end_s")
                        )
                        y_trimmed = np.array(y[..., trim_start:trim_end], copy=True)
                        y_trimmed = fade_in_out(y_trimmed, sr, trim_selection.get("fade_ms", 10.0))
                    else:
                        trim_start_samples = int(recommendations["trim"]["detected_music_start"] * sr)
                        detected_end = recommendations["trim"]["detected_music_end"]
                        trim_end_samples = int(detected_end * sr)
                        buffer_samples = int(0.1 * sr)
                        trim_start = max(0, trim_start_samples - buffer_samples)
                        trim_end = min(y.shape[-1], trim_end_samples + buffer_samples)
                        y_trimmed = y[..., trim_start:trim_end]

                    _write_audio(str(trim_output), y_trimmed, sr, subtype=INTERMEDIATE_WAV_SUBTYPE)
                    current_file = str(trim_output)
                    steps_taken.append({
                        "step": "trim",
                        "trimmed_start_seconds": round(trim_start / sr, 2),
                        "trimmed_end_seconds": round((y.shape[-1] - trim_end) / sr, 2),
                        "output": str(trim_output) if keep_intermediates else "temp"
                    })

            # Step 2b: Hum removal (before broadband noise reduction)
            if recommendations["hum"]["recommended"]:
                logger.info("Step 1b: Hum removal...")
                if keep_intermediates:
                    hum_output = intermediate_dir / "01b_dehummed.wav"
                else:
                    import tempfile
                    hum_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await REGISTRY["remove_hum"].apply(
                    ctx, current_file, str(hum_output),
                    fundamental_hz=recommendations["hum"]["fundamental_hz"],
                    start_s=start_s, end_s=end_s
                )
                if result.get("status") == "success" and result.get("hum_detected"):
                    current_file = str(hum_output)
                    steps_taken.append({
                        "step": "hum_removal",
                        "fundamental_hz": result.get("fundamental_hz"),
                        "harmonics_notched": result.get("harmonics_notched"),
                        "output": str(hum_output) if keep_intermediates else "temp"
                    })

            # Step 3: Noise reduction
            if recommendations["noise_reduction"]["recommended"]:
                logger.info("Step 2: Noise reduction...")
                recommended_strength = recommendations["noise_reduction"]["recommended_strength"]
                strength = step_param("noise_reduction", "reduction_strength", recommended_strength * mult)
                strength = min(1.0, max(0.0, strength))
                profile_duration = step_param(
                    "noise_reduction", "noise_profile_duration",
                    recommendations["noise_reduction"]["recommended_profile_duration"]
                )
                non_stationary = step_param("noise_reduction", "non_stationary", False)

                if keep_intermediates:
                    noise_output = intermediate_dir / "02_denoised.wav"
                else:
                    import tempfile
                    noise_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await REGISTRY["reduce_noise"].apply(
                    ctx, current_file, profile_duration, strength, str(noise_output),
                    subtype=INTERMEDIATE_WAV_SUBTYPE, start_s=start_s, end_s=end_s,
                    non_stationary=non_stationary
                )
                if result.get("status") == "success":
                    current_file = str(noise_output)
                    steps_taken.append({
                        "step": "noise_reduction",
                        "strength": round(strength, 2),
                        "reduction_db": result.get("noise_reduction_db"),
                        "output": str(noise_output) if keep_intermediates else "temp"
                    })

            # Step 4: EQ
            if recommendations["eq"]["recommended"]:
                logger.info("Step 3: Applying EQ...")
                eq_adjustments = recommendations["eq"]["adjustments"]
                high_pass_freq = None
                low_pass_freq = None
                eq_bands = []
                for adj in eq_adjustments:
                    if adj["type"] == "high_pass":
                        high_pass_freq = adj["frequency"]
                    elif adj["type"] == "low_pass":
                        low_pass_freq = adj["frequency"]
                    elif adj["type"] in ("boost", "reduce"):
                        eq_bands.append({"frequency": adj["frequency"], "gain_db": adj["amount"] * mult})

                high_pass_freq = step_param("eq", "high_pass_freq", high_pass_freq)
                low_pass_freq = step_param("eq", "low_pass_freq", low_pass_freq)
                eq_bands = step_param("eq", "bands", eq_bands)

                if keep_intermediates:
                    eq_output = intermediate_dir / "03_eq.wav"
                else:
                    import tempfile
                    eq_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await REGISTRY["apply_eq"].apply(
                    ctx, current_file, high_pass_freq or 30, low_pass_freq, None, 0,
                    str(eq_output), eq_bands=eq_bands or None, subtype=INTERMEDIATE_WAV_SUBTYPE,
                    start_s=start_s, end_s=end_s
                )
                if result.get("status") == "success":
                    current_file = str(eq_output)
                    steps_taken.append({
                        "step": "eq",
                        "adjustments": eq_adjustments,
                        "high_pass_freq": high_pass_freq,
                        "low_pass_freq": low_pass_freq,
                        "bands": eq_bands,
                        "output": str(eq_output) if keep_intermediates else "temp"
                    })

            # Step 4b: Pitch correction (opt-in)
            if do_pitch:
                logger.info("Step 4b: Pitch correction...")
                if keep_intermediates:
                    pitch_output = intermediate_dir / "04b_pitch.wav"
                else:
                    import tempfile
                    pitch_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await REGISTRY["correct_pitch"].apply(
                    ctx, current_file, step_param("pitch", "semitones", 0),
                    step_param("pitch", "auto_tune", True), str(pitch_output),
                    correction_strength=step_param("pitch", "correction_strength", 1.0),
                    key=step_param("pitch", "key", None),
                    chromatic=step_param("pitch", "chromatic", False),
                    start_s=start_s, end_s=end_s,
                )
                if result.get("status") == "success":
                    current_file = str(pitch_output)
                    steps_taken.append({
                        "step": "pitch",
                        "mode": result.get("mode"),
                        "key": result.get("key"),
                        "notes_corrected": result.get("notes_corrected"),
                        "correction_strength": result.get("correction_strength"),
                        "output": str(pitch_output) if keep_intermediates else "temp"
                    })

            # Step 4c: Tempo (opt-in, whole-track)
            if do_tempo:
                target_bpm = step_param("tempo", "target_bpm", None)
                if target_bpm:
                    logger.info("Step 4c: Tempo correction...")
                    if keep_intermediates:
                        tempo_output = intermediate_dir / "04c_tempo.wav"
                    else:
                        import tempfile
                        tempo_output = Path(tempfile.mktemp(suffix=".wav"))

                    result = await REGISTRY["match_tempo"].apply(
                        ctx, current_file, float(target_bpm), str(tempo_output)
                    )
                    if result.get("status") == "success":
                        current_file = str(tempo_output)
                        steps_taken.append({
                            "step": "tempo",
                            "original_bpm": result.get("original_bpm"),
                            "target_bpm": result.get("target_bpm"),
                            "stretch_ratio": result.get("stretch_ratio"),
                            "output": str(tempo_output) if keep_intermediates else "temp"
                        })

            # Step 5: Normalize
            if do_normalize:
                logger.info("Step 4: Normalization...")
                comp_ratio = recommendations["compression"]["ratio"]
                if aggressiveness == "aggressive":
                    comp_ratio *= 1.2
                elif aggressiveness == "gentle":
                    comp_ratio *= 0.8
                comp_ratio = step_param("normalize", "compression_ratio", comp_ratio)
                target_peak_db = step_param("normalize", "target_peak_db", -3.0)
                apply_compression = step_param("normalize", "apply_compression", True)

                if keep_intermediates:
                    norm_output = intermediate_dir / "04_normalized.wav"
                else:
                    import tempfile
                    norm_output = Path(tempfile.mktemp(suffix=".wav"))

                result = await REGISTRY["normalize_audio"].apply(
                    ctx, current_file, target_peak_db, apply_compression, str(norm_output),
                    subtype=INTERMEDIATE_WAV_SUBTYPE, compression_ratio=comp_ratio
                )
                if result.get("status") == "success":
                    current_file = str(norm_output)
                    steps_taken.append({
                        "step": "normalize",
                        "target_peak_db": target_peak_db,
                        "compression_ratio": comp_ratio if apply_compression else None,
                        "gain_applied_db": result.get("gain_applied_db"),
                        "output": str(norm_output) if keep_intermediates else "temp"
                    })

            # Step 6: Mastering (or final write if disabled)
            if do_master:
                logger.info("Step 5: Mastering...")
                target_lufs = step_param("master", "target_lufs", recommendations["mastering"]["target_lufs"])
                result = await REGISTRY["apply_mastering"].apply(
                    ctx, current_file, target_lufs, output_path
                )
                if result.get("status") == "success":
                    steps_taken.append({
                        "step": "mastering",
                        "target_lufs": target_lufs,
                        "actual_lufs": result.get("actual_loudness_lufs"),
                        "gain_applied_db": result.get("gain_applied_db"),
                        "output": output_path
                    })
            else:
                y_final, sr_final = _load_audio(current_file)
                final_subtype = FINAL_WAV_SUBTYPE if output_path.lower().endswith(".wav") else None
                _write_audio(output_path, y_final, sr_final, subtype=final_subtype)

            if not keep_intermediates:
                for step in steps_taken:
                    if step.get("output") and step["output"] != "temp" and step["output"] != output_path:
                        try:
                            Path(step["output"]).unlink()
                        except Exception:
                            pass

            logger.info(f"Auto-cleaning complete: {len(steps_taken)} steps applied")

            return {
                "status": "success",
                "input_file": file_path,
                "output_file": output_path,
                "aggressiveness": aggressiveness,
                "region": {"start_s": start_s, "end_s": end_s} if has_region else None,
                "analysis_summary": analysis.get("summary"),
                "steps_applied": steps_taken,
                "intermediate_files": str(intermediate_dir) if keep_intermediates else None,
                "output_bit_depth": "24-bit PCM" if output_path.lower().endswith(".wav") else "format default",
                "total_steps": len(steps_taken),
                "recommendations_followed": {
                    "trim": any(s["step"] == "trim" for s in steps_taken),
                    "hum_removal": any(s["step"] == "hum_removal" for s in steps_taken),
                    "noise_reduction": any(s["step"] == "noise_reduction" for s in steps_taken),
                    "eq": any(s["step"] == "eq" for s in steps_taken),
                    "pitch": any(s["step"] == "pitch" for s in steps_taken),
                    "tempo": any(s["step"] == "tempo" for s in steps_taken),
                    "normalize": any(s["step"] == "normalize" for s in steps_taken),
                    "mastering": any(s["step"] == "mastering" for s in steps_taken)
                }
            }

        except Exception as e:
            logger.error(f"Error auto-cleaning recording: {e}")
            return {
                "status": "error",
                "error": str(e),
                "input_file": file_path
            }
