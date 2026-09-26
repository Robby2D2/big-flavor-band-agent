"""Transcribing what was said and sung during a candidate take.

Take boundaries cannot be found from loudness (see ``session_detect``): a band
that keeps noodling while they discuss the last attempt never falls quiet, so
two attempts at one song read as one long stretch, and a stretch of pure chatter
reads as a song. Measured on a real session, rhythm does not separate them
either — the talking scored *higher* on pulse clarity than the song did, because
noodling is rhythmic.

What does separate them is the words. So every candidate region is transcribed
before its boundaries are settled, and ``session_attempts`` turns the transcript
into the takes.

Transcription runs on a **mix of the vocal tracks only**. The band has a mic per
singer, so mixing them puts whoever is singing in front of Whisper without the
instruments, and without the duplicate lines two separately-transcribed mics
would produce from bleed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from src.production import wavpack_io
from src.production.session_detect import Take, Track
from src.production.session_render import mix_audio_files

logger = logging.getLogger("backend-api")

#: Whisper's native rate. Transcribing the vocal mix at anything higher only
#: costs resampling.
TRANSCRIBE_RATE = 16000

#: Whisper segments below this confidence are normally dropped as noise, but a
#: session needs the opposite: mumbled chatter is exactly the signal that splits
#: two attempts, so nothing is filtered out here.
SESSION_MIN_CONFIDENCE = 0.0


@dataclass
class TranscriptLine:
    """One transcribed line, timed against the **session timeline**."""

    start: float
    end: float
    text: str
    confidence: float


def build_vocal_mix(
    take: Take,
    tracks: Sequence[Track],
    sources: dict,
    output_path: str | Path,
) -> Optional[str]:
    """Render the vocal tracks over one region into a single mono file.

    Returns ``None`` when the region has no vocal audio at all, which is a real
    answer — an instrumental stretch has no words to read.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    slices: List[Path] = []
    for index, track in enumerate(tracks):
        if track.role != "vocals":
            continue
        source = sources.get(track.source_name)
        if source is None:
            continue

        # Each track sits at its own timeline position, so the offset into its
        # file is not the same for every track.
        offset = take.start - track.position
        duration = min(take.duration, track.envelope.duration - offset)
        if duration <= 0:
            continue

        piece = output.parent / f"{output.stem}-vox{index}.wav"
        wavpack_io.extract_segment(
            source,
            piece,
            start=max(offset, 0.0),
            duration=duration,
            sample_rate=TRANSCRIBE_RATE,
            channels=1,
        )
        slices.append(piece)

    if not slices:
        return None

    mix_audio_files(slices, output, TRANSCRIBE_RATE)
    for piece in slices:
        piece.unlink(missing_ok=True)
    return str(output)


def transcribe_region(
    audio_path: str | Path, take: Take, extractor
) -> List[TranscriptLine]:
    """Transcribe one region's vocal mix into timeline-relative lines.

    ``extractor`` is a ``src.rag.lyrics_extractor.LyricsExtractor`` — passed in
    rather than built here so a whole session loads Whisper once, the same reason
    ``scripts/backfill_lyric_timings.py`` does it.
    """
    result = extractor.transcribe_audio(
        str(audio_path),
        vad_filter=True,
        # A gap this long is a pause between thoughts or between song sections;
        # shorter splits chop sung phrases into fragments that read as chatter.
        vad_min_silence_ms=1500,
    )
    if result.get("error"):
        logger.warning("Transcription failed for %s: %s", audio_path, result["error"])
        return []

    return [
        TranscriptLine(
            start=take.start + segment["start"],
            end=take.start + segment["end"],
            text=segment["text"].strip(),
            confidence=segment.get("confidence", 0.0),
        )
        for segment in result.get("segments", [])
        if segment.get("text", "").strip()
    ]
