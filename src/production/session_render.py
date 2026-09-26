"""Cutting detected takes out of a session's tracks.

A take is a time range on the session timeline. Rendering one means slicing that
range out of every track that was playing during it — those slices become the
take's stems, with no separation needed, since the band recorded them apart in
the first place — and summing them into the mix that represents the take as a
song.

Slices are written as FLAC: the sources are 24-bit, FLAC keeps that losslessly
in about half the space, and ``soundfile`` reads it, so every existing audio
tool works on a session stem unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from src.production import wavpack_io
from src.production.session_detect import Take, Track

logger = logging.getLogger("backend-api")

#: Stems quieter than this across a whole take held nothing worth keeping — a
#: mic for an instrument nobody played on that song.
STEM_SILENCE_PEAK_DB = -40.0


@dataclass
class RenderedStem:
    """One track's audio for one take."""

    #: Demucs-style bucket, unique within the take (`vocals`, `vocals-2`, ...),
    #: which is the name the audio tools resolve against.
    name: str
    #: The band's own track name, kept for display.
    display_name: str
    path: str
    peak_db: float


@dataclass
class RenderedTake:
    take: Take
    mix_path: str
    stems: List[RenderedStem]
    sample_rate: int


def render_take(
    take: Take,
    tracks: Sequence[Track],
    sources: Dict[str, Path],
    output_dir: str | Path,
    sample_rate: int = 48000,
) -> RenderedTake:
    """Slice one take out of every track and build its mix.

    ``sources`` maps a track's ``source_name`` to the file holding its audio.
    Tracks with no audio in this take's range are dropped, so a song the keys
    player sat out does not carry an empty keys stem.
    """
    output = Path(output_dir)
    (output / "stems").mkdir(parents=True, exist_ok=True)

    used_names: Dict[str, int] = {}
    stems: List[RenderedStem] = []

    for track in tracks:
        source = sources.get(track.source_name)
        if source is None:
            continue

        # The take is on the session timeline; the file starts at the track's
        # own position, which is not the same for every track.
        offset = take.start - track.position
        duration = min(take.duration, track.envelope.duration - offset)
        if duration <= 0:
            continue

        name = _unique_name(track.role, used_names)
        path = output / "stems" / f"{name}.flac"
        wavpack_io.extract_segment(
            source, path, start=max(offset, 0.0), duration=duration,
            sample_rate=sample_rate,
        )

        peak_db = _peak_db(path)
        if peak_db < STEM_SILENCE_PEAK_DB:
            path.unlink(missing_ok=True)
            used_names[track.role] -= 1
            continue

        stems.append(
            RenderedStem(
                name=name,
                display_name=track.name,
                path=str(path),
                peak_db=peak_db,
            )
        )

    mix_path = output / "mix.wav"
    mix_audio_files([stem.path for stem in stems], mix_path, sample_rate)

    return RenderedTake(
        take=take, mix_path=str(mix_path), stems=stems, sample_rate=sample_rate
    )


def _unique_name(role: str, used: Dict[str, int]) -> str:
    """`vocals`, then `vocals-2` — two singers each have their own mic, and a
    stem set keys on this name."""
    used[role] = used.get(role, 0) + 1
    return role if used[role] == 1 else f"{role}-{used[role]}"


def _peak_db(path: Path) -> float:
    import soundfile as sf

    peak = 0.0
    with sf.SoundFile(str(path)) as handle:
        for block in handle.blocks(blocksize=1 << 20, dtype="float32"):
            if block.size:
                peak = max(peak, float(np.max(np.abs(block))))
    return 20.0 * float(np.log10(peak)) if peak > 0 else float("-inf")


def mix_audio_files(
    paths: Sequence[str | Path], output_path: str | Path, sample_rate: int
) -> None:
    """Sum audio files into one mono mix, scaled only if the sum would clip.

    The band's own tracks sum to what was played in the room, so this is a plain
    sum — no balancing. Only the headroom is adjusted, and only when needed, so
    the mix keeps the relative levels the band set.
    """
    import soundfile as sf

    if not paths:
        sf.write(str(output_path), np.zeros(0, dtype="float32"), sample_rate)
        return

    total: Optional[np.ndarray] = None
    for path in paths:
        audio, _ = sf.read(str(path), dtype="float32", always_2d=True)
        mono = audio.mean(axis=1)
        if total is None:
            total = mono
        else:
            length = min(len(total), len(mono))
            total = total[:length] + mono[:length]

    assert total is not None
    peak = float(np.max(np.abs(total))) if total.size else 0.0
    if peak > 1.0:
        total = total / peak

    sf.write(str(output_path), total, sample_rate, subtype="PCM_24")
