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

    result, notices = await produce._chain_apply_tools(
        agent=_AgentNeverCalled(),
        specs=[],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="vocals",
    )

    assert result == source_path
    assert notices == []
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

    result, notices = await produce._chain_apply_tools(
        agent=agent,
        specs=[
            produce.StemFixSpec(tool="reduce_noise"),
            produce.StemFixSpec(tool="apply_eq"),
        ],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="vocals",
    )

    assert notices == [], "tools that did what they said raise nothing"
    assert [c[0] for c in agent.calls] == ["reduce_noise", "apply_eq"]
    # Step 1 reads the original source; step 2 reads step 1's output, not the source.
    assert agent.calls[0][1] == str(source_path)
    assert agent.calls[1][1] == agent.calls[0][2]
    assert agent.calls[1][1] != str(source_path)
    # The chain's return value is step 2's output file, with its content.
    assert result == Path(agent.calls[1][2])
    assert result.read_bytes() == b"after-apply_eq"


class _AgentThatFallsBack:
    """A tool that succeeds but reports doing less than it was asked — what
    ``correct_pitch`` returns when a source turns out not to be a single line."""

    async def execute_tool(self, tool, args):
        Path(args["output_path"]).write_bytes(b"shifted")
        if tool == "correct_pitch":
            return {
                "status": "success",
                "mode": "global_fallback",
                "fallback_reason": "Input does not look like a single line in its "
                                   "loudest 20s; applied a whole-file shift instead.",
            }
        return {"status": "success"}


@pytest.mark.asyncio
async def test_chain_apply_tools_reports_a_fix_that_did_less_than_it_said(tmp_path):
    """A successful-but-downgraded fix has to come back as a notice.

    Accepting a fix and being handed back unchanged audio, with nothing said, is
    the outcome issue #91 exists to prevent. The chain used to read each result
    only for ``status``, so ``fallback_reason`` could not reach the producer at
    all — the render simply looked like it had worked.
    """
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"original")

    result, notices = await produce._chain_apply_tools(
        agent=_AgentThatFallsBack(),
        specs=[
            produce.StemFixSpec(tool="reduce_noise"),
            produce.StemFixSpec(tool="correct_pitch"),
        ],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="guitar",
    )

    assert result.exists()
    assert len(notices) == 1, notices
    assert notices[0]["tool"] == "correct_pitch"
    # The scope is the row the producer is looking at, so a notice can be read
    # without cross-referencing which stem it came from.
    assert notices[0]["scope"] == "guitar"
    assert "single line" in notices[0]["reason"]


@pytest.mark.asyncio
async def test_notice_scope_names_the_row_not_the_run_directory(tmp_path):
    """A single-stem preview needs a unique directory per run, and still has to
    tell the producer which row the notice is about — so ``scope`` is separate
    from the directory ``tag``. Without this the UI would show a timestamp."""
    source_path = tmp_path / "source.wav"
    source_path.write_bytes(b"original")

    _result, notices = await produce._chain_apply_tools(
        agent=_AgentThatFallsBack(),
        specs=[produce.StemFixSpec(tool="correct_pitch")],
        source_path=source_path,
        output_dir=tmp_path / "out",
        tag="run1790001977094",
        scope="vocals",
    )

    assert notices[0]["scope"] == "vocals"
    # ...while the intermediate files still live under the unique run tag.
    assert (tmp_path / "out" / "run1790001977094").exists()
