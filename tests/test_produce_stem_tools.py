"""Tests for the per-stem audio-tool API (Console redesign): the confidence
tagging helper every tool's ``analyze()`` uses, and the two new orchestration
primitives in ``src/api/routers/produce.py`` — resolving a tool's source audio
to an individual stem (with the song-ownership check that keeps a caller from
pointing at another song's stem), and chain-applying a list of fixes.

Assert-based, no live DB, no LLM, no Demucs — matching the pattern in
test_stem_separation.py's ``FakeDB``.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.routers import produce
from src.production.toolkit import AudioTool


# ---- AudioTool.confidence_tier ----

def test_confidence_tier_high_worth_low():
    # Higher magnitude = stronger evidence (the default direction every tool uses).
    assert AudioTool.confidence_tier(10.0, high=8.0, worth=3.0) == "high"
    assert AudioTool.confidence_tier(5.0, high=8.0, worth=3.0) == "worth_a_listen"
    assert AudioTool.confidence_tier(1.0, high=8.0, worth=3.0) is None
    # A None input (nothing measured) never crashes the threshold comparison.
    assert AudioTool.confidence_tier(None, high=8.0, worth=3.0) is None


def test_confidence_tier_lower_is_worse_direction():
    # higher_is_worse=False: a *smaller* value is the stronger signal.
    assert AudioTool.confidence_tier(1.0, high=2.0, worth=5.0, higher_is_worse=False) == "high"
    assert AudioTool.confidence_tier(4.0, high=2.0, worth=5.0, higher_is_worse=False) == "worth_a_listen"
    assert AudioTool.confidence_tier(9.0, high=2.0, worth=5.0, higher_is_worse=False) is None


# ---- _resolve_tool_source_path / _resolve_stem_path ----

class FakeDB:
    """Minimal in-memory stand-in for the stem/version DB methods the router uses."""

    def __init__(self):
        self.stems = {}
        self.stem_sets = {}

    async def get_stem(self, stem_id):
        return self.stems.get(stem_id)

    async def get_stem_set(self, stem_set_id):
        return self.stem_sets.get(stem_set_id)

    async def get_song_version(self, version_id):
        return None


@pytest.mark.asyncio
async def test_resolve_tool_source_path_stem_mismatch_404(tmp_path):
    """A stem belonging to a *different* song's stem set 404s, not silently resolves."""
    stem_path = tmp_path / "vocals.wav"
    stem_path.write_bytes(b"not-really-audio")

    db = FakeDB()
    db.stem_sets[1] = {"id": 1, "song_id": 999, "status": "complete"}
    db.stems[7] = {"id": 7, "stem_set_id": 1, "name": "vocals", "path": str(stem_path)}

    with pytest.raises(HTTPException) as exc_info:
        await produce._resolve_tool_source_path(
            song_id=5, source_version_id=None, stem_id=7, db=db
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_tool_source_path_stem_id_missing_404():
    db = FakeDB()
    with pytest.raises(HTTPException) as exc_info:
        await produce._resolve_tool_source_path(
            song_id=5, source_version_id=None, stem_id=404, db=db
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_tool_source_path_matching_stem_resolves(tmp_path):
    """The happy path: a stem owned by the requested song resolves to its file."""
    stem_path = tmp_path / "vocals.wav"
    stem_path.write_bytes(b"not-really-audio")

    db = FakeDB()
    db.stem_sets[1] = {"id": 1, "song_id": 5, "status": "complete"}
    db.stems[7] = {"id": 7, "stem_set_id": 1, "name": "vocals", "path": str(stem_path)}

    resolved = await produce._resolve_tool_source_path(
        song_id=5, source_version_id=None, stem_id=7, db=db
    )
    assert resolved == stem_path


# ---- _chain_apply_tools ----

class _AgentNeverCalled:
    """Fails the test if execute_tool is invoked — used to prove the empty-specs
    path short-circuits before touching the agent at all."""

    async def execute_tool(self, tool, args):
        raise AssertionError("execute_tool should not be called for an empty fix chain")


@pytest.mark.asyncio
async def test_chain_apply_tools_empty_specs_passthrough(tmp_path):
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"not-really-audio")

    result = await produce._chain_apply_tools(
        agent=_AgentNeverCalled(),
        specs=[],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="vocals",
    )

    assert result == source_path
    # No intermediate directory should have been created for a no-op chain.
    assert not (tmp_path / "out" / "vocals").exists()


class _AgentChainRecorder:
    """Records each execute_tool call's input/output paths and writes a
    placeholder output file, so a multi-step chain's output-feeds-next-input
    wiring can be asserted."""

    def __init__(self):
        self.calls = []  # (tool, file_path, output_path)

    async def execute_tool(self, tool, args):
        self.calls.append((tool, args["file_path"], args["output_path"]))
        Path(args["output_path"]).write_bytes(f"after-{tool}".encode())
        return {"status": "success"}


@pytest.mark.asyncio
async def test_chain_apply_tools_feeds_output_to_next_step(tmp_path):
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"original")
    agent = _AgentChainRecorder()

    result = await produce._chain_apply_tools(
        agent=agent,
        specs=[
            produce.StemFixSpec(tool="reduce_noise"),
            produce.StemFixSpec(tool="apply_eq"),
        ],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="vocals",
    )

    assert [c[0] for c in agent.calls] == ["reduce_noise", "apply_eq"]
    # Step 1 reads the original source; step 2 reads step 1's output, not the source.
    assert agent.calls[0][1] == str(source_path)
    assert agent.calls[1][1] == agent.calls[0][2]
    assert agent.calls[1][1] != str(source_path)
    # The chain's return value is step 2's output file, with its content.
    assert result == Path(agent.calls[1][2])
    assert result.read_bytes() == b"after-apply_eq"
