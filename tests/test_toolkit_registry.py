"""Tests for the per-tool audio toolkit: the registry, each tool's MCP schema,
argument coercion, and a per-tool analyze() round-trip on synthesized audio.

No DB/LLM/MCP transport — the registry and tools are exercised directly.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("mcp")
pytest.importorskip("librosa")

from src.production.toolkit import REGISTRY, AudioTool, Param, ToolContext

SR = 22050

# Every tool that must ship as its own file.
EXPECTED_TOOLS = {
    "analyze_audio", "match_tempo", "correct_beats", "create_transition",
    "apply_mastering", "get_audio_cache_stats", "trim_silence", "reduce_noise",
    "remove_hum", "correct_pitch", "normalize_audio", "apply_eq", "remove_artifacts",
}


def test_registry_discovers_every_tool():
    assert EXPECTED_TOOLS <= set(REGISTRY), (
        f"missing tools: {EXPECTED_TOOLS - set(REGISTRY)}"
    )
    for name, tool in REGISTRY.items():
        assert isinstance(tool, AudioTool)
        assert tool.name == name


def test_each_tool_emits_a_valid_mcp_schema():
    for name, tool in REGISTRY.items():
        mcp_tool = tool.to_mcp_tool()
        assert mcp_tool.name == name
        assert mcp_tool.description
        schema = mcp_tool.inputSchema
        assert schema["type"] == "object"
        assert isinstance(schema["properties"], dict)
        # required entries must be real properties
        for req in schema.get("required", []):
            assert req in schema["properties"]


def test_tool_info_exposes_param_controls():
    info = REGISTRY["reduce_noise"].tool_info()
    assert info["name"] == "reduce_noise"
    names = {p["name"] for p in info["params"]}
    # standard + tool-specific params both present
    assert {"file_path", "output_path", "reduction_strength", "start_s", "strength"} <= names
    rs = next(p for p in info["params"] if p["name"] == "reduction_strength")
    assert rs["default"] == 0.7 and rs["min"] == 0 and rs["max"] == 1


def test_coerce_args_fills_defaults_and_drops_unknown():
    tool = REGISTRY["trim_silence"]
    out = tool.coerce_args({"file_path": "a.wav", "output_path": "b.wav",
                            "bogus": 1, "start_s": 3.0})
    assert "bogus" not in out
    assert out["threshold_db"] == -40   # default filled
    assert out["start_s"] == 3.0        # provided wins
    assert out["trim_to_selection"] is False


def test_coerce_args_raises_on_missing_required():
    with pytest.raises(ValueError):
        REGISTRY["match_tempo"].coerce_args({"file_path": "a.wav", "output_path": "b.wav"})


def _synth_wav(path: Path):
    import soundfile as sf
    t = np.arange(0, 4.0, 1 / SR)
    y = np.zeros_like(t)
    mid = (t > 1.0) & (t < 3.0)
    y[mid] = 0.3 * np.sin(2 * np.pi * 220 * t[mid]) + 0.2 * np.sin(2 * np.pi * 110 * t[mid])
    y += 0.02 * np.sin(2 * np.pi * 60 * t)      # mains hum
    y += 0.001 * np.random.RandomState(0).randn(len(t))
    sf.write(path, y.astype(np.float32), SR)


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", [
    "trim_silence", "reduce_noise", "remove_hum", "apply_eq",
    "normalize_audio", "apply_mastering", "correct_beats",
])
async def test_analyze_returns_normalized_shape(tool_name, tmp_path):
    wav = tmp_path / "in.wav"
    _synth_wav(wav)
    ctx = ToolContext(enable_audio_analysis=False)
    result = await REGISTRY[tool_name].analyze(ctx, str(wav))
    assert result["status"] == "success"
    assert result["tool"] == tool_name
    assert isinstance(result["recommended"], bool)
    assert isinstance(result["params"], dict)


@pytest.mark.asyncio
async def test_analyze_detects_the_planted_hum(tmp_path):
    wav = tmp_path / "in.wav"
    _synth_wav(wav)
    ctx = ToolContext(enable_audio_analysis=False)
    result = await REGISTRY["remove_hum"].analyze(ctx, str(wav))
    assert result["recommended"] is True
    assert result["params"]["fundamental_hz"] in (50.0, 60.0)


@pytest.mark.asyncio
async def test_server_analyze_tool_routes_and_reports_unknown(tmp_path):
    """BigFlavorMCPServer.analyze_tool (the /tools/{tool}/analyze seam) runs the
    tool's analyze and reports unknown tools as an error."""
    from src.production.big_flavor_mcp import BigFlavorMCPServer

    wav = tmp_path / "in.wav"
    _synth_wav(wav)
    server = BigFlavorMCPServer(enable_audio_analysis=False)

    ok = await server.analyze_tool("apply_eq", {"file_path": str(wav)})
    assert ok["status"] == "success"
    assert ok["tool"] == "apply_eq"

    bad = await server.analyze_tool("does_not_exist", {"file_path": str(wav)})
    assert "error" in bad
