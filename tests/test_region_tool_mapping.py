"""Assert-based tests for the region-editor tool mapping (issue #70).

Exercises ``build_region_tool_args`` — the pure mapper from a friendly editor
tool name + selected region to a concrete MCP editing-tool call — without the
FastAPI app, database, or any LLM. Confirms each tool maps to the right MCP
tool, region/strength/params are forwarded correctly, and unknown tools error.
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.region_tools import REGION_TOOLS, build_region_tool_args

SRC = "/audio/1_orig.mp3"
OUT = "/produced/1_preview.wav"


def test_all_advertised_tools_map():
    """Every whitelisted tool maps to an MCP tool with file/output paths set."""
    for tool in REGION_TOOLS:
        name, args = build_region_tool_args(tool, 1.0, 2.0, 0.8, {}, SRC, OUT)
        assert name, f"{tool} produced no MCP tool name"
        assert args["file_path"] == SRC
        assert args["output_path"] == OUT


def test_unknown_tool_raises():
    with pytest.raises(ValueError):
        build_region_tool_args("reverb", 1.0, 2.0, 1.0, {}, SRC, OUT)


def test_trim_is_trim_to_selection_with_region():
    name, args = build_region_tool_args("trim", 3.0, 7.5, 1.0, {}, SRC, OUT)
    assert name == "trim_silence"
    assert args["trim_to_selection"] is True
    assert args["start_s"] == 3.0
    assert args["end_s"] == 7.5


def test_noise_reduction_forwards_region_strength_and_params():
    name, args = build_region_tool_args(
        "noise_reduction",
        4.0,
        9.0,
        0.5,
        {"non_stationary": True, "noise_start_s": 0.0, "noise_end_s": 1.0},
        SRC,
        OUT,
    )
    assert name == "reduce_noise"
    assert args["start_s"] == 4.0 and args["end_s"] == 9.0
    assert args["strength"] == 0.5
    assert args["non_stationary"] is True
    assert args["noise_start_s"] == 0.0 and args["noise_end_s"] == 1.0


def test_pitch_defaults_to_autotune_with_strength_as_retune():
    name, args = build_region_tool_args(
        "pitch", 2.0, 3.0, 0.9, {"key": "A minor"}, SRC, OUT
    )
    assert name == "correct_pitch"
    assert args["auto_tune"] is True
    assert args["correction_strength"] == 0.9
    assert args["key"] == "A minor"


def test_tempo_is_whole_file_no_region_forwarded():
    name, args = build_region_tool_args(
        "tempo", 5.0, 10.0, 0.4, {"target_bpm": 120}, SRC, OUT
    )
    assert name == "correct_beats"
    # correct_beats has no region parameter — bounds must not be forwarded.
    assert "start_s" not in args and "end_s" not in args
    assert args["strength"] == 0.4
    assert args["target_bpm"] == 120


def test_eq_forwards_bands_and_region():
    bands = [{"frequency": 200, "gain_db": -3}]
    name, args = build_region_tool_args(
        "eq", 0.0, 4.0, 1.0, {"eq_bands": bands}, SRC, OUT
    )
    assert name == "apply_eq"
    assert args["eq_bands"] == bands
    assert args["start_s"] == 0.0 and args["end_s"] == 4.0


def test_unknown_params_are_dropped():
    _name, args = build_region_tool_args(
        "eq", 0.0, 1.0, 1.0, {"evil_arg": "rm -rf", "high_pass_freq": 40}, SRC, OUT
    )
    assert "evil_arg" not in args
    assert args["high_pass_freq"] == 40
