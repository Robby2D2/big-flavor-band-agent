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


@dataclass
class SplitPart:
    """One side of a take cut in two: its mix and the channels that kept audio."""

    mix_path: str
    stems: List[RenderedStem]


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


def split_rendered_take(
    mix_path: str | Path,
    stems: Sequence[RenderedStem],
    at_seconds: float,
    before_dir: str | Path,
    after_dir: str | Path,
) -> tuple[SplitPart, SplitPart]:
    """Cut a rendered take in two at ``at_seconds`` into the take.

    Works from the take's own files, not the session's tracks: the raw WavPack
    is gone once a scan finishes. Cutting the mix at the same sample as its
    channels gives what re-summing them would, so nothing is mixed again. A
    channel left silent on one side is dropped there, as ``render_take`` does.
    """
    parts = []
    for directory, start, end in (
        (Path(before_dir), 0.0, at_seconds),
        (Path(after_dir), at_seconds, None),
    ):
        part_mix = directory / "mix.wav"
        slice_audio_file(mix_path, part_mix, start, end)
        part_stems = []
        for stem in stems:
            path = directory / "stems" / Path(stem.path).name
            slice_audio_file(stem.path, path, start, end)
            peak_db = _peak_db(path)
            if peak_db < STEM_SILENCE_PEAK_DB:
                path.unlink(missing_ok=True)
                continue
            part_stems.append(
                RenderedStem(
                    name=stem.name,
                    display_name=stem.display_name,
                    path=str(path),
                    peak_db=peak_db,
                )
            )
        parts.append(SplitPart(mix_path=str(part_mix), stems=part_stems))
    return parts[0], parts[1]


def slice_audio_file(
    source: str | Path,
    target: str | Path,
    start_seconds: float,
    end_seconds: Optional[float] = None,
) -> None:
    """Copy ``[start, end)`` of an audio file, keeping its format and bit depth.

    Streamed in blocks: a take stem is up to half an hour of 48 kHz audio.
    """
    import soundfile as sf

    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sf.SoundFile(str(source)) as src:
        first = min(int(round(start_seconds * src.samplerate)), src.frames)
        last = src.frames
        if end_seconds is not None:
            last = min(int(round(end_seconds * src.samplerate)), src.frames)
        src.seek(first)
        with sf.SoundFile(
            str(target), "w",
            samplerate=src.samplerate, channels=src.channels,
            format=src.format, subtype=src.subtype,
        ) as dst:
            remaining = max(0, last - first)
            while remaining:
                block = src.read(min(remaining, 1 << 20), dtype="float32", always_2d=True)
                if not len(block):
                    break
                dst.write(block)
                remaining -= len(block)


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
