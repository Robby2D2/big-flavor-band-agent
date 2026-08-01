"""Per-tool audio-processing contract + registry.

Every audio tool is a small self-contained :class:`AudioTool` subclass in its
own file under ``src/production/tools/``. A tool declares:

* ``name`` / ``summary`` / ``description`` — identity + human copy.
* ``params`` — a list of :class:`Param` describing the *adjustable* knobs a
  client can show and tweak **before** running the tool.
* ``analyze(ctx, file_path, **params)`` — inspect only; report what the tool
  *would* do (findings the UI shows for review).
* ``apply(ctx, file_path, output_path, **params)`` — do the processing.

The ``@register`` decorator adds the tool to :data:`REGISTRY`, which the MCP
server and the FastAPI layer iterate over — so adding a new effect is exactly
"add one file". Standard params shared by almost every tool (``file_path``,
``output_path``, region bounds, wet/dry ``strength``) are injected by flags so a
tool only spells out its own knobs.

This module is deliberately dependency-light (no FastAPI/DB/librosa imports) so
it can be imported and unit-tested in isolation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Type

logger = logging.getLogger("big-flavor-mcp")

try:  # mcp is always present at runtime; guarded so tests can import the module bare
    from mcp.types import Tool
except Exception:  # pragma: no cover - mcp missing in some tooling contexts
    Tool = None  # type: ignore


# --------------------------------------------------------------------------- #
# Param — one adjustable knob, rendered as a UI control and as JSON schema.
# --------------------------------------------------------------------------- #

# Python type -> JSON-schema "type" string.
_JSON_TYPES: Dict[type, str] = {
    float: "number",
    int: "integer",
    bool: "boolean",
    str: "string",
    list: "array",
    dict: "object",
}


@dataclass
class Param:
    """A single tunable parameter for a tool.

    Carries enough metadata for a frontend to render a control (label, range,
    default) and for :meth:`AudioTool.to_mcp_tool` to emit a JSON schema.
    """

    name: str
    type: type = float
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    label: Optional[str] = None
    help: Optional[str] = None
    required: bool = False
    choices: Optional[List[Any]] = None
    # Escape hatch for complex shapes (arrays of objects, nested objects): when
    # set it is used verbatim as the JSON-schema fragment for this property.
    schema: Optional[Dict[str, Any]] = None

    def json_schema(self) -> Dict[str, Any]:
        """JSON-schema fragment for this param (the value under ``properties``)."""
        if self.schema is not None:
            frag = dict(self.schema)
        else:
            frag = {"type": _JSON_TYPES.get(self.type, "string")}
            if self.minimum is not None:
                frag["minimum"] = self.minimum
            if self.maximum is not None:
                frag["maximum"] = self.maximum
            if self.choices is not None:
                frag["enum"] = list(self.choices)
        desc = self.help or self.label
        if desc:
            frag.setdefault("description", desc)
        return frag

    def ui_meta(self) -> Dict[str, Any]:
        """Compact description a client uses to render + validate a control."""
        return {
            "name": self.name,
            "type": _JSON_TYPES.get(self.type, "string"),
            "default": self.default,
            "min": self.minimum,
            "max": self.maximum,
            "label": self.label or self.name.replace("_", " ").title(),
            "help": self.help,
            "required": self.required,
            "choices": self.choices,
        }


# Reusable standard params, injected by the flags on AudioTool below so tools
# don't re-spell the ones nearly all of them share.
def _file_param() -> Param:
    return Param("file_path", str, required=True, label="Input file",
                 help="Path to the audio file to process")


def _output_param() -> Param:
    return Param("output_path", str, required=True, label="Output file",
                 help="Path to write the processed file")


def _region_params() -> List[Param]:
    return [
        Param("start_s", float, label="Region start (s)",
              help="Optional start of the time range (seconds); omit to process the whole file"),
        Param("end_s", float, label="Region end (s)",
              help="Optional end of the time range (seconds); omit to process through the end"),
    ]


def _strength_param() -> Param:
    return Param(
        "strength", float, default=1.0, minimum=0.0, maximum=1.0,
        label="Effect strength",
        help="Wet/dry blend 0-1 (1.0 = full effect); 0 leaves the region unchanged",
    )


# --------------------------------------------------------------------------- #
# AudioTool — the base class every tool subclasses.
# --------------------------------------------------------------------------- #

class AudioTool:
    """Base class for a self-contained audio-processing tool.

    Subclasses set the class attributes and implement :meth:`apply` (and, once
    it has real analysis, :meth:`analyze`). The positional order of ``apply``'s
    parameters after ``ctx`` is significant: the compatibility shim in
    ``BigFlavorMCPServer`` binds ``ctx`` and forwards the remaining positional
    args, so keep ``apply(self, ctx, file_path, ..., output_path, ...)`` in the
    same order the legacy method used.
    """

    #: Unique tool name (matches the MCP tool name and the dispatch key).
    name: str = ""
    #: One-line human summary (drives the UI tool list).
    summary: str = ""
    #: Full MCP description; falls back to ``summary`` when unset.
    description: str = ""
    #: Tool-specific tunable params (standard ones are injected via the flags).
    params: List[Param] = []

    # Standard-param injection flags.
    takes_file: bool = True
    takes_output: bool = True
    takes_region: bool = False
    takes_strength: bool = False

    # Whole-song orchestrators (auto-clean) set this so the per-tool editor panel
    # hides them — they are pipelines, not single effects.
    hidden_from_editor: bool = False

    # ---- schema plumbing --------------------------------------------------- #

    @classmethod
    def all_params(cls) -> List[Param]:
        """Standard + tool-specific params in a stable, UI-friendly order."""
        out: List[Param] = []
        if cls.takes_file:
            out.append(_file_param())
        if cls.takes_output:
            out.append(_output_param())
        out.extend(cls.params)
        if cls.takes_region:
            out.extend(_region_params())
        if cls.takes_strength:
            out.append(_strength_param())
        return out

    @classmethod
    def input_schema(cls) -> Dict[str, Any]:
        """The MCP/JSON inputSchema built from :meth:`all_params`."""
        props: Dict[str, Any] = {}
        required: List[str] = []
        for p in cls.all_params():
            props[p.name] = p.json_schema()
            if p.required:
                required.append(p.name)
        schema: Dict[str, Any] = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        return schema

    @classmethod
    def to_mcp_tool(cls):
        """Build the ``mcp.types.Tool`` advertised by ``list_tools``."""
        if Tool is None:  # pragma: no cover
            raise RuntimeError("mcp is not importable; cannot build Tool")
        return Tool(
            name=cls.name,
            description=cls.description or cls.summary,
            inputSchema=cls.input_schema(),
        )

    @classmethod
    def tool_info(cls) -> Dict[str, Any]:
        """UI-facing descriptor: name, summary, and each param's control meta.

        ``applies_to_file`` is True for tools that transform a single input file
        into an output (they take both ``file_path`` and ``output_path``) — the
        ones the produce editor can Analyze → Apply. Analysis-only or
        multi-input tools (e.g. ``analyze_audio``, ``create_transition``) are
        False, so the UI can hide them from the per-tool editing panel.
        """
        return {
            "name": cls.name,
            "summary": cls.summary,
            "description": cls.description or cls.summary,
            "applies_to_file": bool(cls.takes_file and cls.takes_output),
            "hidden_from_editor": bool(cls.hidden_from_editor),
            "params": [p.ui_meta() for p in cls.all_params()],
        }

    @classmethod
    def coerce_args(cls, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Map ``arguments`` to this tool's declared params as keyword args.

        Unknown keys are dropped (a client can never inject an arbitrary kwarg);
        a provided value wins; an omitted optional param falls back to its
        declared default; a missing *required* param raises ``ValueError``. Every
        declared param is present in the result, so ``apply`` can be called with
        keywords only and never trips over a missing positional.
        """
        provided = arguments or {}
        out: Dict[str, Any] = {}
        for p in cls.all_params():
            if p.name in provided and provided[p.name] is not None:
                out[p.name] = provided[p.name]
            elif p.required:
                raise ValueError(f"{cls.name}: missing required argument '{p.name}'")
            else:
                out[p.name] = p.default
        return out

    # ---- behavior (subclasses override) ----------------------------------- #

    async def analyze(self, ctx: "ToolContext", file_path: str, **params) -> dict:
        """Inspect only; report what :meth:`apply` would do.

        Base implementation is a no-op stub returning ``recommended: False``;
        tools with detectable issues override this (Phase 2).
        """
        return {
            "status": "success",
            "tool": self.name,
            "recommended": False,
            "message": f"No analysis available for '{self.name}'",
        }

    @staticmethod
    def confidence_tier(
        value: Optional[float], high: float, worth: float, higher_is_worse: bool = True
    ) -> Optional[str]:
        """Bucket a measured magnitude into a review-queue confidence tag.

        ``"high"`` / ``"worth_a_listen"`` / ``None`` (not worth flagging), so a
        tool's ``analyze()`` can turn one already-computed number (a dB level, a
        count, a confidence score) into the tag a fix card shows, without every
        tool re-deriving its own tiering. ``higher_is_worse`` picks the
        direction: True when a larger value is stronger evidence for the fix
        (e.g. noise floor dB, count of imbalances), False when a smaller value
        is (e.g. a distance-from-target that should shrink).
        """
        if value is None:
            return None
        if higher_is_worse:
            if value > high:
                return "high"
            if value > worth:
                return "worth_a_listen"
            return None
        if value < high:
            return "high"
        if value < worth:
            return "worth_a_listen"
        return None

    async def apply(self, ctx: "ToolContext", *args, **kwargs) -> dict:
        raise NotImplementedError(f"{self.name}.apply is not implemented")


# --------------------------------------------------------------------------- #
# ToolContext — the shared services the server hands each tool.
# --------------------------------------------------------------------------- #

@dataclass
class ToolContext:
    """Shared services a tool may need, decoupled from the server object.

    Replaces the old ``self.db_manager`` / ``self._get_cached_analysis`` coupling
    so tools never reach back into ``BigFlavorMCPServer``. The analysis-cache
    helpers moved here verbatim from the server.
    """

    db_manager: Any = None
    enable_audio_analysis: bool = True

    @staticmethod
    def file_hash(file_path: str) -> str:
        """Calculate MD5 hash of a file."""
        import hashlib

        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    async def get_cached_analysis(self, file_path: str, file_hash: str) -> Optional[dict]:
        """Get cached analysis from the database."""
        if not self.db_manager:
            return None
        try:
            query = """
                SELECT analysis_data
                FROM audio_analysis_cache
                WHERE file_path = $1 AND file_hash = $2
            """
            async with self.db_manager.pool.acquire() as conn:
                row = await conn.fetchrow(query, file_path, file_hash)
                if row:
                    return row["analysis_data"]
        except Exception as e:
            logger.warning(f"Error checking cache: {e}")
        return None

    async def save_analysis_to_cache(self, file_path: str, file_hash: str, analysis: dict) -> None:
        """Save analysis to the database cache."""
        if not self.db_manager:
            return
        try:
            query = """
                INSERT INTO audio_analysis_cache (file_path, file_hash, analysis_data, analyzed_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (file_path)
                DO UPDATE SET
                    file_hash = EXCLUDED.file_hash,
                    analysis_data = EXCLUDED.analysis_data,
                    analyzed_at = EXCLUDED.analyzed_at
            """
            async with self.db_manager.pool.acquire() as conn:
                await conn.execute(query, file_path, file_hash, analysis)
            logger.info(f"Saved analysis to cache for {file_path}")
        except Exception as e:
            logger.warning(f"Error saving to cache: {e}")


# --------------------------------------------------------------------------- #
# Registry.
# --------------------------------------------------------------------------- #

REGISTRY: Dict[str, AudioTool] = {}


def register(cls: Type[AudioTool]) -> Type[AudioTool]:
    """Class decorator: instantiate the tool and add it to :data:`REGISTRY`."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must set a non-empty 'name'")
    if cls.name in REGISTRY:
        raise ValueError(f"Duplicate tool name registered: {cls.name}")
    REGISTRY[cls.name] = cls()
    return cls


def get_tool(name: str) -> Optional[AudioTool]:
    return REGISTRY.get(name)
