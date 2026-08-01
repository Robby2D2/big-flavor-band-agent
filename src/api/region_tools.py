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

# Friendly editor tool name -> the registered MCP tool whose declared params it
# forwards. The per-tool param whitelist below is *derived* from each tool's own
# ``Param`` declarations (single source of truth), so adding a knob to a tool
# exposes it to the region editor automatically.
_FRIENDLY_TO_MCP = {
    "trim": "trim_silence",
    "noise_reduction": "reduce_noise",
    "pitch": "correct_pitch",
    "tempo": "correct_beats",
    "eq": "apply_eq",
}

# Params the editor manages itself (source/output paths, region bounds, the
# wet/dry strength, and the ones ``build_region_tool_args`` sets from the
# region/strength below) — excluded from the client-forwardable set so a client
# can't override the editor's own wiring.
_MANAGED_PARAMS = {
    "file_path", "output_path", "start_s", "end_s", "strength",
    "correction_strength", "trim_to_selection",
}

# Hardcoded fallback, used only where the production tool package can't be
# imported (a lean CI runner without librosa/mcp). Kept in sync with the derived
# set; the derived set is authoritative when available.
_FALLBACK_REGION_TOOL_PARAMS = {
    "trim": ("fade_ms", "threshold_db"),
    "noise_reduction": (
        "reduction_strength", "non_stationary", "noise_start_s",
        "noise_end_s", "noise_profile_duration", "highpass_hz",
    ),
    "pitch": ("key", "chromatic", "semitones", "auto_tune"),
    "tempo": ("target_bpm",),
    "eq": ("high_pass_freq", "low_pass_freq", "boost_freq", "boost_db", "eq_bands"),
}


def _derive_region_tool_params():
    """Whitelist of forwardable params per friendly tool, from the registry."""
    try:
        from src.production import REGISTRY
    except Exception:  # pragma: no cover - lean env without the production stack
        return dict(_FALLBACK_REGION_TOOL_PARAMS)

    derived = {}
    for friendly, mcp_name in _FRIENDLY_TO_MCP.items():
        tool = REGISTRY.get(mcp_name)
        if tool is None:
            derived[friendly] = _FALLBACK_REGION_TOOL_PARAMS.get(friendly, ())
            continue
        derived[friendly] = tuple(
            p.name for p in tool.all_params() if p.name not in _MANAGED_PARAMS
        )
    return derived


_REGION_TOOL_PARAMS = _derive_region_tool_params()


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
