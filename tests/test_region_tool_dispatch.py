"""Dispatch-path tests for the region editor (issue #70 QA follow-up).

The pure mapper (``tests/test_region_tool_mapping.py``) proves the friendly
tool name + region map to the right MCP tool + args, but it never exercises the
code that *consumes* that mapping — which is exactly where the region/strength
kwargs were being silently dropped and ``correct_beats`` was unknown. These
tests drive the actual dispatch the /produce region endpoints use:

1. ``BigFlavorAgent.execute_tool`` -> the production dispatch (the seam the
   endpoints call) forwards the full arg dict and routes every region tool,
   including ``correct_beats``.
2. ``BigFlavorMCPServer.dispatch_tool`` -> the leaf tool actually receives the
   region bounds / strength / per-tool params (not a positional subset).

Both use fakes/spies — no real DSP, LLM, or DB — so a dropped-kwarg or
unknown-tool regression fails in pytest, not just in a browser.
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.api.region_tools import REGION_TOOLS, build_region_tool_args

SRC = "/audio/1_orig.mp3"
OUT = "/produced/1_preview.wav"

# A representative region + params per tool, mirroring what the waveform editor
# sends, so we assert the region/strength/params actually survive dispatch.
_TOOL_CASES = {
    "trim": (3.0, 7.5, 1.0, {"fade_ms": 20.0}),
    "noise_reduction": (4.0, 9.0, 0.5, {"non_stationary": True, "noise_start_s": 0.0}),
    "pitch": (2.0, 3.0, 0.9, {"key": "A minor"}),
    "tempo": (5.0, 10.0, 0.4, {"target_bpm": 120}),
    "eq": (0.0, 4.0, 1.0, {"eq_bands": [{"frequency": 200, "gain_db": -3}]}),
}


class _RecordingProductionServer:
    """Stands in for the MCP production server at the agent seam.

    Captures exactly what ``BigFlavorAgent`` hands to the single dispatch path,
    so the test can assert the whole arg dict (region bounds, strength, params)
    is forwarded verbatim rather than a stale positional subset.
    """

    def __init__(self):
        self.calls = []

    async def dispatch_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return {"status": "success"}


def _make_agent(production_server):
    """Build a BigFlavorAgent without its heavy __init__ (LLM/DB/MCP)."""
    from src.agent.big_flavor_agent import BigFlavorAgent

    agent = BigFlavorAgent.__new__(BigFlavorAgent)
    agent.production_server = production_server
    agent.rag_system = None
    return agent


@pytest.mark.asyncio
async def test_agent_forwards_full_region_args_for_every_tool():
    """execute_tool must route every region tool and forward the mapper's full
    arg dict unchanged — the exact regression that shipped broken (kwargs
    dropped, whole-file processing at default strength)."""
    server = _RecordingProductionServer()
    agent = _make_agent(server)

    for tool in REGION_TOOLS:
        start_s, end_s, strength, params = _TOOL_CASES[tool]
        tool_name, args = build_region_tool_args(
            tool, start_s, end_s, strength, params, SRC, OUT
        )

        result = await agent.execute_tool(tool_name, args)

        assert result.get("status") == "success", (
            f"{tool} did not reach the production dispatch: {result}"
        )
        assert server.calls, f"{tool} never dispatched"
        dispatched_name, dispatched_args = server.calls[-1]
        assert dispatched_name == tool_name
        # The whole arg dict must survive — no silent positional truncation.
        assert dispatched_args == args


@pytest.mark.asyncio
async def test_agent_routes_correct_beats_not_unknown_tool():
    """Tempo maps to correct_beats; before the fix that fell through to
    {"error": "Unknown tool: correct_beats"} and the endpoint 502'd."""
    server = _RecordingProductionServer()
    agent = _make_agent(server)

    tool_name, args = build_region_tool_args(
        "tempo", 0.0, 5.0, 0.6, {"target_bpm": 128}, SRC, OUT
    )
    assert tool_name == "correct_beats"

    result = await agent.execute_tool(tool_name, args)

    assert result.get("status") == "success"
    assert "error" not in result
    assert server.calls[-1][0] == "correct_beats"
    assert server.calls[-1][1]["strength"] == 0.6
    assert server.calls[-1][1]["target_bpm"] == 128


@pytest.mark.asyncio
async def test_mcp_dispatch_delivers_region_kwargs_to_leaf_tools():
    """The single dispatcher must hand region bounds / strength / params to the
    actual tool method — proving the seam beneath the agent honors them too.

    Skips where the heavy production deps (mcp/librosa/soundfile) aren't
    installed (e.g. a lean CI runner); the agent-seam tests above always run.
    """
    pytest.importorskip("mcp")
    pytest.importorskip("librosa")
    from src.production.big_flavor_mcp import BigFlavorMCPServer

    server = BigFlavorMCPServer(enable_audio_analysis=False)

    captured = {}

    def _spy(tool_name):
        async def _recorder(*args, **kwargs):
            captured[tool_name] = {"args": args, "kwargs": kwargs}
            return {"status": "success"}

        return _recorder

    for leaf in ("trim_silence", "reduce_noise", "correct_pitch", "apply_eq", "correct_beats"):
        setattr(server, leaf, _spy(leaf))

    for tool in REGION_TOOLS:
        start_s, end_s, strength, params = _TOOL_CASES[tool]
        tool_name, args = build_region_tool_args(
            tool, start_s, end_s, strength, params, SRC, OUT
        )
        result = await server.dispatch_tool(tool_name, args)
        assert result.get("status") == "success", f"{tool_name} failed dispatch: {result}"

    # trim -> trim_silence keeps the selected span with its region bounds.
    assert captured["trim_silence"]["kwargs"]["start_s"] == 3.0
    assert captured["trim_silence"]["kwargs"]["end_s"] == 7.5
    assert captured["trim_silence"]["kwargs"]["trim_to_selection"] is True

    # noise reduction -> region + wet/dry strength + adaptive flag.
    assert captured["reduce_noise"]["kwargs"]["start_s"] == 4.0
    assert captured["reduce_noise"]["kwargs"]["end_s"] == 9.0
    assert captured["reduce_noise"]["kwargs"]["strength"] == 0.5
    assert captured["reduce_noise"]["kwargs"]["non_stationary"] is True

    # pitch -> region + retune strength as correction_strength.
    assert captured["correct_pitch"]["kwargs"]["start_s"] == 2.0
    assert captured["correct_pitch"]["kwargs"]["correction_strength"] == 0.9
    assert captured["correct_pitch"]["kwargs"]["key"] == "A minor"

    # eq -> region + strength + bands.
    assert captured["apply_eq"]["kwargs"]["start_s"] == 0.0
    assert captured["apply_eq"]["kwargs"]["strength"] == 1.0
    assert captured["apply_eq"]["kwargs"]["eq_bands"] == [{"frequency": 200, "gain_db": -3}]

    # tempo -> correct_beats reached with strength (whole-file by design).
    assert captured["correct_beats"]["kwargs"]["strength"] == 0.4
    assert captured["correct_beats"]["kwargs"]["target_bpm"] == 120


@pytest.mark.asyncio
async def test_mcp_dispatch_unknown_tool_returns_error():
    pytest.importorskip("mcp")
    pytest.importorskip("librosa")
    from src.production.big_flavor_mcp import BigFlavorMCPServer

    server = BigFlavorMCPServer(enable_audio_analysis=False)
    result = await server.dispatch_tool("does_not_exist", {"file_path": SRC})
    assert "error" in result
