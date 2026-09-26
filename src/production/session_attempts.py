"""Turning a region's transcript into the band's attempts at songs.

A candidate region from ``session_detect`` is a stretch where somebody was
playing. That is not the same as a song: the band runs a song, talks about it
while noodling, and runs it again, all without falling quiet. The words are what
separate those, so this module reads the transcript.

The split of work matters. The model is asked only to label each line
``lyrics`` or ``chatter`` — a per-line judgement it is good at. Every span
decision is then arithmetic in Python, because it is not: asked directly for
attempt spans, the local 14B split one attempt in two and returned a stretch of
chatter as an attempt while its own reasoning said it was chatter. Measured on a
real session's transcript, per-line labelling scored 16/18 zero-shot, and both
errors were single lines flipped inside a long run of lyrics — which
:func:`smooth_labels` removes by construction.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.production.session_detect import MIN_TAKE_SECONDS, Take
from src.production.session_transcribe import TranscriptLine

logger = logging.getLogger("backend-api")

LYRICS = "lyrics"
CHATTER = "chatter"

#: How many chatter lines in a row it takes to end an attempt. One is not
#: enough: a single misread line inside a song would split it, and that is the
#: model's typical error.
MIN_CHATTER_RUN = 2

#: How long the band must fall quiet for it to count as having *stopped*, rather
#: than simply left a gap between notes. Measured on a real session: the longest
#: gap inside a guitar solo was 1.0s, while the gap between two attempts at one
#: song was 5.7s.
MIN_STOP_SECONDS = 2.0

#: How many transcript lines go to the model at once. See :func:`label_lines`
#: for why it is neither the whole pass nor one region.
LABEL_BATCH = 20

SYSTEM_PROMPT = """You label lines from a transcript of a band's rehearsal recording.

Each line is either:
  "lyrics"  - words being SUNG as part of a song
  "chatter" - people TALKING: counting in, discussing the arrangement, joking, studio talk

Chatter sounds like conversation directed at other people in the room
("let's do it again", "you guys", "all right", "one more time", "hello").
Lyrics sound like song words, often poetic, and often repeated across the transcript.

Reply with JSON only, one label per input line, in the same order:
{"labels": ["lyrics", "chatter", ...]}"""


@dataclass
class Attempt:
    """One run at a song, with the words sung during it."""

    take: Take
    lines: List[TranscriptLine]

    @property
    def text(self) -> str:
        return " ".join(line.text for line in self.lines).strip()


async def attempts_for_regions(
    transcripts: Sequence[tuple[Take, Sequence[TranscriptLine]]],
    llm,
    activity=None,
) -> List[List[Attempt]]:
    """Split every region of one recording pass into attempts.

    The pass's lines are labelled as **one stream**, not region by region,
    because the judgement is comparative: "it's all good it's all good" reads
    like a hook on its own and the model duly called it singing, but set beside
    the pass's actual lyrics it reads as what it is. A short region's few lines
    therefore travel in a batch with its neighbours' — see :func:`label_lines`
    for how that stream is batched.
    """
    lines_per_region = [list(lines) for _, lines in transcripts]
    flat = [line for lines in lines_per_region for line in lines]
    labels = await label_lines(flat, llm)

    results: List[List[Attempt]] = []
    cursor = 0
    for (region, _), lines in zip(transcripts, lines_per_region):
        # Smoothing is per region: two lines either side of a region boundary are
        # minutes apart, so a lone chatter line there is not "surrounded" by the
        # singing that happens to sit next to it in the flat list.
        span = smooth_labels(labels[cursor : cursor + len(lines)])
        cursor += len(lines)
        results.append(attempts_from_labels(region, lines, span, activity=activity))
    return results


async def label_lines(lines: Sequence[TranscriptLine], llm) -> List[str]:
    """Label each transcript line ``lyrics`` or ``chatter``.

    Lines are labelled in batches of :data:`LABEL_BATCH`, drawn from the pass in
    order, which is a compromise between the two ways this measurably fails. A
    batch of the whole pass (86 lines) degraded badly — the model flipped a
    stretch of obvious chatter to singing. A batch of one short region gave it
    nothing to compare against, and "it's all good it's all good" reads like a
    hook when it stands alone. Twenty-odd lines of a rehearsal holds both
    singing and talking, so each has the other for contrast.
    """
    if not lines:
        return []

    labels: List[str] = []
    for start in range(0, len(lines), LABEL_BATCH):
        batch = lines[start : start + LABEL_BATCH]
        labels.extend(await _label_batch(batch, llm))
    return labels


async def _label_batch(lines: Sequence[TranscriptLine], llm) -> List[str]:
    """Label one batch.

    Degrades rather than raises, like every other parser of local-model output
    in this project: an unreadable reply means "we cannot tell singing from
    talking here", which leaves the audio in place for a human to split, and is
    always better than discarding a real take.
    """
    numbered = "\n".join(f"{index + 1}. {line.text}" for index, line in enumerate(lines))
    try:
        reply = await llm.generate_response(
            messages=[{"role": "user", "content": numbered}],
            system=SYSTEM_PROMPT,
            max_tokens=64 + 8 * len(lines),
            temperature=0.0,
        )
    except Exception:
        logger.exception("Line labelling failed; treating the region as unsplittable")
        return [LYRICS] * len(lines)

    labels = _parse_labels(reply, len(lines))
    if labels is None:
        logger.warning(
            "Could not read labels from the model; treating the region as unsplittable"
        )
        return [LYRICS] * len(lines)
    return labels


def _parse_labels(reply: str, expected: int) -> Optional[List[str]]:
    """Read the ``labels`` array out of a model reply, or None if unreadable."""
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    if not match:
        return None
    try:
        raw = json.loads(match.group(0)).get("labels")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(raw, list):
        return None

    labels = [
        CHATTER if str(value).strip().lower().startswith("chat") else LYRICS
        for value in raw
    ]
    if len(labels) < expected:
        # A short reply is not a failure — the lines it did not reach are the
        # ones we know least about, and calling them lyrics keeps their audio.
        labels += [LYRICS] * (expected - len(labels))
    return labels[:expected]


def smooth_labels(labels: Sequence[str], min_chatter_run: int = MIN_CHATTER_RUN) -> List[str]:
    """Promote short runs of chatter inside singing back to lyrics.

    The model's characteristic error is one line flipped in the middle of a long
    lyric run. A real gap between attempts is people talking for a while, which
    is several lines — so a run shorter than ``min_chatter_run`` is noise.

    A short chatter run at either end of the region is left alone: an attempt
    that begins or ends with a count-in has no lyric run on that side to have
    been broken out of.
    """
    smoothed = list(labels)
    for start, length in _chatter_runs(smoothed):
        if length >= min_chatter_run:
            continue
        surrounded = start > 0 and start + length < len(smoothed)
        if surrounded:
            smoothed[start : start + length] = [LYRICS] * length
    return smoothed


def _chatter_runs(labels: Sequence[str]) -> List[tuple[int, int]]:
    runs: List[tuple[int, int]] = []
    index = 0
    while index < len(labels):
        if labels[index] != CHATTER:
            index += 1
            continue
        start = index
        while index < len(labels) and labels[index] == CHATTER:
            index += 1
        runs.append((start, index - start))
    return runs


def attempts_from_labels(
    region: Take,
    lines: Sequence[TranscriptLine],
    labels: Sequence[str],
    activity=None,
) -> List[Attempt]:
    """Split a region into attempts at songs.

    Two rules, each judged by the signal that can actually judge it:

    * **The band stopping is what ends an attempt** — they cannot start a song
      again without having stopped it. So the boundaries are the sustained
      silences in ``activity``, and nothing else. Talking is *not* a boundary: a
      rehearsal is full of it during a song, shouted over a solo or on the way
      into a verse, and splitting there cuts the song in half. Conversely a
      restart needs no discussion at all, so waiting for talking would miss one.
    * **Singing is what makes a stretch a song.** A span between two stops that
      nobody sang over is talking, tuning or noodling — not an attempt.

    With no ``activity`` to consult the whole region is one attempt, since
    nothing can then say whether the band ever stopped.
    """
    if not lines:
        # Nothing was said or sung. It could be an instrumental, so the region
        # is kept whole rather than thrown away on no evidence.
        return [Attempt(take=region, lines=[])]

    sung = [line for line, label in zip(lines, labels) if label == LYRICS]
    if not sung:
        return []

    attempts: List[Attempt] = []
    for begin, finish in _spans_between_stops(region, activity):
        held = [line for line in sung if begin <= _midpoint(line) < finish]
        if held:
            attempts.append(Attempt(take=Take(start=begin, end=finish), lines=held))
    return [a for a in attempts if a.take.duration >= MIN_TAKE_SECONDS]


def _spans_between_stops(region: Take, activity) -> List[tuple[float, float]]:
    """The region, cut at every point the band stopped playing.

    Spans reach right up to each stop, so a song keeps its instrumental intro
    and its final chord: everything between one silence and the next belongs to
    whatever was played there.
    """
    spans: List[tuple[float, float]] = []
    cursor = region.start
    for quiet_start, quiet_end in _stops(activity, region.start, region.end):
        if quiet_start > cursor:
            spans.append((cursor, quiet_start))
        cursor = max(cursor, quiet_end)
    if cursor < region.end:
        spans.append((cursor, region.end))
    return spans


def _midpoint(line: TranscriptLine) -> float:
    """Which span a line belongs to is decided by its middle, so a line that
    straddles a stop lands on the side it mostly sits in."""
    return (line.start + line.end) / 2.0


def _stops(activity, begin: float, end: float) -> List[tuple[float, float]]:
    """Intervals in ``[begin, end)`` where the band genuinely stopped playing.

    A stop has to be *sustained*. Measured over a real guitar solo, the gaps
    between notes ran to 1.0s at the longest, while the real gap between two
    attempts at a song was 5.7s — so :data:`MIN_STOP_SECONDS` sits between them,
    and a run of note gaps can never be mistaken for the band stopping.
    """
    if activity is None or end <= begin:
        return []
    import numpy as np

    fps = activity.fps
    first = max(int((begin - activity.start) * fps), 0)
    last = min(int((end - activity.start) * fps), len(activity.playing))
    if last <= first:
        return []

    window = activity.playing[first:last]
    minimum = MIN_STOP_SECONDS * fps
    stops: List[tuple[float, float]] = []
    changes = np.flatnonzero(window[1:] != window[:-1]) + 1
    bounds = np.concatenate(([0], changes, [window.size]))
    for start, stop in zip(bounds[:-1], bounds[1:]):
        if not window[start] and (stop - start) >= minimum:
            stops.append(
                (
                    activity.start + (first + int(start)) / fps,
                    activity.start + (first + int(stop)) / fps,
                )
            )
    return stops
