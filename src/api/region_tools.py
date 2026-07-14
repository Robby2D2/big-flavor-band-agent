"""Region-editor tool mapping (issue #70).

The waveform editor sends a friendly tool name plus a selected region and a
wet/dry strength; this maps that to a concrete v0.14.0 MCP editing-tool call.
Pure and dependency-free (no FastAPI/DB/LLM imports) so it can be unit-tested in
isolation and reused by both the preview and apply endpoints.
"""

from typing import Any, Dict, Optional, Tuple

# Friendly editor tool name -> the MCP editing tool it drives. Every one of these
# already accepts start_s/end_s and (except trim/tempo) a wet/dry strength, so the
# editor never touches the DSP — it only supplies the region and parameters.
REGION_TOOLS = ("trim", "noise_reduction", "pitch", "tempo", "eq")

# Per-tool params the editor may forward. Whitelisted so a client can never inject
# an arbitrary MCP argument; unknown keys are dropped.
_REGION_TOOL_PARAMS = {
    "trim": ("fade_ms", "threshold_db"),
    "noise_reduction": (
        "reduction_strength", "non_stationary", "noise_start_s",
        "noise_end_s", "noise_profile_duration", "highpass_hz",
    ),
    "pitch": ("key", "chromatic", "semitones", "auto_tune"),
    "tempo": ("target_bpm",),
    "eq": ("high_pass_freq", "low_pass_freq", "boost_freq", "boost_db", "eq_bands"),
}


def build_region_tool_args(
    tool: str,
    start_s: Optional[float],
    end_s: Optional[float],
    strength: float,
    params: Optional[Dict[str, Any]],
    file_path: str,
    output_path: str,
) -> Tuple[str, Dict[str, Any]]:
    """Map an editor tool + region to a concrete MCP tool call.

    Returns ``(mcp_tool_name, arguments)``. Raises ``ValueError`` for an unknown
    tool. ``trim`` is trim-to-selection (keep the selected span); ``tempo``
    (``correct_beats``) is whole-file by design — beat correction has no region
    parameter — so its region bounds are intentionally not forwarded.
    """
    if tool not in REGION_TOOLS:
        raise ValueError(f"Unsupported tool: {tool}")

    params = params or {}
    allowed = _REGION_TOOL_PARAMS[tool]
    extra = {k: params[k] for k in allowed if params.get(k) is not None}

    args: Dict[str, Any] = {"file_path": file_path, "output_path": output_path}

    if tool == "trim":
        # Keep only the selected span (discard outside it), with a smooth edge.
        args.update(trim_to_selection=True, start_s=start_s, end_s=end_s)
        args.update(extra)
        return "trim_silence", args

    if tool == "noise_reduction":
        args.update(start_s=start_s, end_s=end_s, strength=strength)
        args.update(extra)
        return "reduce_noise", args

    if tool == "pitch":
        # Auto-tune (per-note, key-aware) is the region-editor default; strength
        # is the retune amount. Manual transpose still works via params.semitones.
        args.update(
            start_s=start_s,
            end_s=end_s,
            auto_tune=extra.pop("auto_tune", True),
            correction_strength=strength,
        )
        args.update(extra)
        return "correct_pitch", args

    if tool == "tempo":
        args.update(strength=strength)
        args.update(extra)
        return "correct_beats", args

    # eq
    args.update(start_s=start_s, end_s=end_s, strength=strength)
    args.update(extra)
    return "apply_eq", args
