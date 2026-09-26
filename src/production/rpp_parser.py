"""Reaper project (``.RPP``) parsing for recording-session import.

A ``.RPP`` is a plain-text tree of ``<CHUNK ...>`` blocks. We only care about
three things: the tracks, the media items on them, and which press of record
each item belongs to. Everything else (FX chains, envelopes, MIDI) is skipped.

Three facts about real sessions drive the shape of this module, all observed in
the band's own projects rather than assumed:

* **``RECPASS`` groups items into recording passes.** Every item Reaper records
  carries the number of the press of record that produced it, so grouping items
  across tracks into "one continuous recording" needs no inference from
  timestamps or positions.
* **One project file spans many sessions.** The band keeps recording into the
  same project, so a ``.RPP`` references passes from earlier nights whose media
  lives in a different project folder entirely. A zip of one session ships only
  that session's audio, so items whose source file is absent are *normal* and
  must be skipped, not treated as corruption.
* **Tracks within a pass do not share a start.** A player who arms late gets an
  item positioned later than the rest — measured at +145s on one guitar track.
  ``POSITION`` is therefore the only truth about where an item sits on the
  timeline; assuming every file starts together silently destroys sync.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

logger = logging.getLogger("backend-api")

# `NAME "quoted value"` / `POSITION 12.5` — a chunk field is a bare token
# followed by the rest of the line.
_FIELD = re.compile(r"^(?P<key>[A-Z_0-9]+)(?:\s+(?P<value>.*))?$")


@dataclass
class Item:
    """One media item: a slice of a source file placed on the timeline."""

    track_name: str
    #: Timeline position, in seconds, of the item's start.
    position: float
    #: Duration in seconds.
    length: float
    #: Offset into the source file at which the item starts (Reaper's SOFFS).
    start_offset: float
    #: Which press of record produced this item (Reaper's RECPASS).
    rec_pass: Optional[int]
    #: The source file, exactly as the project references it (may be absolute
    #: and point outside this project's folder).
    source_file: str
    #: Source chunk type — WAVPACK, WAVE, MIDI, ...
    source_type: str
    #: Reaper's per-item playback rate. Anything but 1.0 means the item's audio
    #: is time-stretched relative to the timeline, which we do not handle.
    play_rate: float = 1.0
    muted: bool = False

    @property
    def end(self) -> float:
        return self.position + self.length

    @property
    def source_name(self) -> str:
        """The source file's basename, which is how a zip's members match up."""
        return Path(self.source_file.replace("\\", "/")).name


@dataclass
class RecordingPass:
    """Every item recorded by one press of record, across all tracks."""

    number: int
    items: List[Item] = field(default_factory=list)

    @property
    def start(self) -> float:
        return min(item.position for item in self.items)

    @property
    def end(self) -> float:
        return max(item.end for item in self.items)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Project:
    """The parts of a parsed ``.RPP`` that session import cares about."""

    #: Track names in project order, including tracks that hold no audio items.
    track_names: List[str]
    items: List[Item]

    def passes(self) -> List[RecordingPass]:
        """Group audio items by ``RECPASS``, in timeline order.

        Items with no ``RECPASS`` (imported media rather than recorded) are
        grouped under pass 0 rather than dropped, so nothing vanishes silently.
        """
        by_number: Dict[int, RecordingPass] = {}
        for item in self.items:
            number = item.rec_pass or 0
            by_number.setdefault(number, RecordingPass(number)).items.append(item)
        return sorted(by_number.values(), key=lambda p: p.start)


def parse_project(path: str | Path) -> Project:
    """Parse a ``.RPP`` into its tracks and audio items.

    Only audio items are returned — a MIDI item has no source audio to scan, so
    it would just be a track that never appears to play.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    return parse_project_text(text)


def parse_project_text(text: str) -> Project:
    """Parse project text. Split out from :func:`parse_project` so tests can
    exercise the grammar without a file on disk."""
    track_names: List[str] = []
    items: List[Item] = []

    # The whole file is one <REAPER_PROJECT> chunk, so tracks live one level in.
    root = next(_chunks(_lines(text), "REAPER_PROJECT"), None)
    if root is None:
        raise ValueError("Not a Reaper project: no <REAPER_PROJECT> chunk")

    for track_chunk in _chunks(iter(root), "TRACK"):
        name = _field(track_chunk, "NAME") or ""
        track_names.append(name)
        for item_chunk in _chunks(iter(track_chunk), "ITEM"):
            item = _parse_item(item_chunk, name)
            if item is not None:
                items.append(item)

    return Project(track_names=track_names, items=items)


def _parse_item(chunk: List[str], track_name: str) -> Optional[Item]:
    """Build an :class:`Item` from an ITEM chunk's lines, or None if it holds no
    audio source."""
    source_chunks = list(_chunks(iter(chunk), "SOURCE"))
    if not source_chunks:
        return None

    # An item with several takes has one SOURCE per take; the first is the
    # active one, which is what Reaper plays and therefore what we scan.
    source = source_chunks[0]
    source_type = _chunk_header(chunk, "SOURCE")
    if source_type == "MIDI":
        return None

    source_file = _field(source, "FILE")
    if not source_file:
        return None

    position = _float(chunk, "POSITION")
    length = _float(chunk, "LENGTH")
    if position is None or length is None:
        logger.warning("Skipping item on %r with no POSITION/LENGTH", track_name)
        return None

    return Item(
        track_name=track_name,
        position=position,
        length=length,
        start_offset=_float(chunk, "SOFFS") or 0.0,
        rec_pass=_int(chunk, "RECPASS"),
        source_file=source_file,
        source_type=source_type or "",
        play_rate=_float(chunk, "PLAYRATE") or 1.0,
        muted=(_int(chunk, "MUTE") or 0) == 1,
    )


def _lines(text: str) -> Iterator[str]:
    return iter(text.splitlines())


def _chunks(lines: Iterator[str], name: str) -> Iterator[List[str]]:
    """Yield the body lines of each top-level ``<NAME ...>`` chunk in ``lines``.

    Bodies are yielded with nested chunks intact, so a caller can recurse into
    them. Depth is tracked over the whole stream rather than by indentation,
    because a project's own text is not reliably indented.
    """
    depth = 0
    body: Optional[List[str]] = None
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("<"):
            depth += 1
            if depth == 1:
                # A chunk opens at depth 1: start collecting if it's ours.
                body = [] if _header_name(stripped) == name else None
                continue
        elif stripped == ">":
            depth -= 1
            if depth == 0:
                if body is not None:
                    yield body
                body = None
                continue
            if depth < 0:
                # Unbalanced close — we were handed a chunk body, so a closing
                # line that pops past our start just ends the stream.
                return
        if depth >= 1 and body is not None:
            body.append(raw)


def _header_name(line: str) -> str:
    """``<TRACK {GUID}`` -> ``TRACK``."""
    return line[1:].split(None, 1)[0] if len(line) > 1 else ""


def _chunk_header(chunk: List[str], name: str) -> Optional[str]:
    """The argument on a nested chunk's opening line: ``<SOURCE WAVPACK`` -> ``WAVPACK``."""
    for raw in chunk:
        stripped = raw.strip()
        if stripped.startswith("<") and _header_name(stripped) == name:
            parts = stripped[1:].split(None, 1)
            return parts[1].strip() if len(parts) > 1 else ""
    return None


def _field(chunk: List[str], key: str) -> Optional[str]:
    """The first value of ``key`` at this chunk's own level.

    Nested chunks are skipped, so a track's ``NAME`` is never shadowed by the
    ``NAME`` of an item or an FX plugin inside it.
    """
    depth = 0
    for raw in chunk:
        stripped = raw.strip()
        if stripped.startswith("<"):
            depth += 1
            continue
        if stripped == ">":
            depth -= 1
            continue
        if depth != 0:
            continue
        match = _FIELD.match(stripped)
        if match and match.group("key") == key:
            value = (match.group("value") or "").strip()
            return _unquote(value)
    return None


def _unquote(value: str) -> str:
    """Strip Reaper's quoting. It picks a quote character the value lacks, so
    `"`, `'` and `` ` `` are all possible delimiters."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        return value[1:-1]
    return value


def _float(chunk: List[str], key: str) -> Optional[float]:
    """First whitespace-separated token of ``key``, as a float."""
    return _numeric(chunk, key, float)


def _int(chunk: List[str], key: str) -> Optional[int]:
    return _numeric(chunk, key, int)


def _numeric(chunk: List[str], key: str, cast):
    value = _field(chunk, key)
    if not value:
        return None
    try:
        return cast(value.split()[0])
    except (ValueError, IndexError):
        return None
