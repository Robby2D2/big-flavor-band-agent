"""
Big Flavor Band MCP Server
A Model Context Protocol server for audio production and analysis operations.
This server handles WRITE/PRODUCTION operations only.
READ/SEARCH operations are handled by the RAG system.

Every audio tool — the single effects *and* the whole-song orchestrators
(``analyze_and_recommend_processing``, ``auto_clean_recording``) — lives
one-per-file under ``src/production/tools/`` and registers itself into
``toolkit.REGISTRY``; this module is a thin *host* that advertises them
(``list_tools``), routes ``apply`` calls (``dispatch_tool``) and ``analyze``
calls (``analyze_tool``) to them, and carries no audio logic of its own. Shared
DSP helpers live in ``audio_io`` / ``analysis`` and are re-exported here so
existing ``from ...big_flavor_mcp import _detect_beats`` style imports keep
working.
"""

import asyncio
import json
import logging
from typing import Any, Optional, List
from pathlib import Path
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import from database package
from database import DatabaseManager

# The tool registry + shared helpers. Imported to work whether the package is
# loaded as ``src.production`` (tests) or with this directory on sys.path (how
# the agent loads it — ``from big_flavor_mcp import BigFlavorMCPServer``).
try:
    from .toolkit import AudioTool, ToolContext, REGISTRY
    from . import tools as _tools  # noqa: F401  (import side effect registers tools)
    from .region import apply_to_region, blend_strength, fade_in_out, resolve_region
    from .audio_io import (
        _load_audio, _to_mono, _apply_per_channel, _write_audio,
        INTERMEDIATE_WAV_SUBTYPE, FINAL_WAV_SUBTYPE, LIBROSA_AVAILABLE,
    )
    from .analysis import (
        _detect_beats, _target_grid, _build_time_map, _apply_time_map,
        _parse_key, _detect_key, _snap_midi, _scale_midi_set,
        detect_hum, measure_integrated_lufs,
    )
except ImportError:  # pragma: no cover - flat sys.path loading
    from toolkit import AudioTool, ToolContext, REGISTRY
    import tools as _tools  # noqa: F401
    from region import apply_to_region, blend_strength, fade_in_out, resolve_region
    from audio_io import (
        _load_audio, _to_mono, _apply_per_channel, _write_audio,
        INTERMEDIATE_WAV_SUBTYPE, FINAL_WAV_SUBTYPE, LIBROSA_AVAILABLE,
    )
    from analysis import (
        _detect_beats, _target_grid, _build_time_map, _apply_time_map,
        _parse_key, _detect_key, _snap_midi, _scale_midi_set,
        detect_hum, measure_integrated_lufs,
    )

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("big-flavor-mcp")


class BigFlavorMCPServer:
    """MCP Server host for Big Flavor audio production and analysis operations."""

    def __init__(self, enable_audio_analysis: bool = True):
        self.app = Server("big-flavor-production-server")
        self.enable_audio_analysis = enable_audio_analysis
        self.db_manager = None
        # Shared services every registered tool receives (DB + analysis cache).
        self._ctx = ToolContext(db_manager=None, enable_audio_analysis=enable_audio_analysis)
        self.setup_handlers()

    async def initialize(self):
        """Initialize database connection."""
        try:
            self.db_manager = DatabaseManager()
            await self.db_manager.connect()
            self._ctx.db_manager = self.db_manager
            logger.info("Database connection initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")

    def __getattr__(self, name: str):
        """Expose each registered tool as ``server.<tool_name>(...)``.

        A thin backward-compatible shim: ``server.reduce_noise(path, ...)``
        resolves to the registered tool's ``apply`` bound to this server's
        ``ToolContext``, preserving the positional-arg method API that existing
        tests and the auto-clean orchestrator use. Only consulted when normal
        attribute lookup fails, so an explicitly-set attribute (e.g. a test spy)
        always wins.
        """
        reg = REGISTRY
        if name in reg:
            import functools
            ctx = self.__dict__.get("_ctx")
            return functools.partial(reg[name].apply, ctx)
        raise AttributeError(name)

    # ------------------------------------------------------------------ #
    # Tool listing + dispatch (generic over the registry).
    # ------------------------------------------------------------------ #

    def list_tools(self) -> list:
        """Every registered tool's MCP schema (generic over the registry)."""
        return [t.to_mcp_tool() for t in REGISTRY.values()]

    def setup_handlers(self):
        """Wire the MCP protocol handlers to the generic list/dispatch."""

        @self.app.list_tools()
        async def list_tools() -> list[Tool]:
            """List available audio production tools."""
            return self.list_tools()

        @self.app.call_tool()
        async def call_tool(name: str, arguments: Any) -> list[TextContent]:
            """Handle MCP tool execution requests (protocol wrapper)."""
            result = await self.dispatch_tool(name, arguments)
            return [TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]

    async def dispatch_tool(self, name: str, arguments: Any) -> dict:
        """Route a production-tool call to its handler and return the raw result.

        Registered tools are looked up in the registry, their arguments coerced
        against the tool's declared params (unknown keys dropped, defaults
        filled), and dispatched through ``getattr(self, name)`` so a tool called
        as ``server.<name>`` and a tool called through the MCP protocol take the
        identical path (and a test spy set on the instance still intercepts).
        Used both by the MCP protocol handler above and by
        ``BigFlavorAgent.execute_tool`` (which the region editor's preview/apply
        endpoints call), so the two can never drift on which kwargs reach a tool
        (issues #65-#70).
        """
        try:
            if name in REGISTRY:
                kwargs = REGISTRY[name].coerce_args(arguments)
                handler = getattr(self, name)
                return await handler(**kwargs)
            return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return {"error": str(e)}

    async def analyze_tool(self, name: str, arguments: Any) -> dict:
        """Run a registered tool's ``analyze`` (inspect-only) pass.

        The read side of the per-tool contract: reports what ``apply`` would do
        (findings + recommended params) without processing anything. Region
        bounds and any tool params in ``arguments`` are forwarded.
        """
        tool = REGISTRY.get(name)
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        try:
            args = dict(arguments or {})
            file_path = args.pop("file_path")
            start_s = args.pop("start_s", None)
            end_s = args.pop("end_s", None)
            args.pop("output_path", None)  # not meaningful for analyze
            return await tool.analyze(self._ctx, file_path, start_s=start_s, end_s=end_s, **args)
        except Exception as e:
            logger.error(f"Error analyzing with tool {name}: {e}")
            return {"error": str(e)}

    async def run(self):
        """Run the MCP server."""
        await self.initialize()

        async with stdio_server() as (read_stream, write_stream):
            await self.app.run(
                read_stream,
                write_stream,
                self.app.create_initialization_options()
            )


async def main():
    """Main entry point for the MCP server."""
    server = BigFlavorMCPServer(enable_audio_analysis=True)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
