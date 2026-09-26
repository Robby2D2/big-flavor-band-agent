"""Finding the songs inside a recorded rehearsal session.

The band leaves Reaper recording for a whole session, so one recording pass is
an unbroken hour holding several songs, several attempts at the same song, and
all the talking in between. This module turns that into **takes**: the stretches
where the band was actually playing.

Detection works on loudness envelopes rather than the audio itself (see
``wavpack_io.envelope``), which makes a session scan cost about a minute.

Two properties of a live band room shape the rules:

* **Every mic hears every instrument.** Bleed means a loud drum hit lights up
  the vocal mics too, so "how many tracks are active" says less than it looks
  like it should. Each track is judged against *its own* quiet level, and the
  decision to call it music leans on the tracks that carry rhythm.
* **Silence between takes is not silence.** It is talking, tuning and chairs.
  So a take ends on a drop in *musical* activity sustained for several seconds,
  not on a drop to a noise floor that never arrives.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np

from src.production.wavpack_io import Envelope

logger = logging.getLogger("backend-api")

# --- Track classification -------------------------------------------------
# Reaper track names are the band's own ("4 Kev Vox", "7 DRUM Mic"), so the
# stem bucket is read off the name and only falls back to the AudioSet tagger
# when the name says nothing. Buckets match Demucs' source names, which is what
# the fix tools resolve against.
# Band members' names appear in track names ("4 Kev Vox", "8 Tom Vox"), so a
# pattern has to survive being a person. `tom` is deliberately absent: this band
# has a Tom, and a drum tom is spelled `toms` or `rack/floor tom` often enough
# that matching the bare word mislabels a human being's tracks.
_ROLE_PATTERNS: Sequence[tuple[str, str]] = (
    (r"\bvox\b|\bvocal", "vocals"),
    (
        r"\bdrum|\bkick\b|\bsnare\b|\btoms\b|(?:rack|floor)\s+tom|\bhat\b|overhead",
        "drums",
    ),
    (r"\bbass\b", "bass"),
    (r"guitar|\bgtr\b|electric|acoustic|\bac g\b|pickup|collings", "guitar"),
    (r"\bkeys?\b|piano|organ|serum|synth", "piano"),
)

#: Roles whose activity is the strongest evidence that a song is underway
#: rather than a conversation.
RHYTHM_ROLES = frozenset({"drums", "bass"})

# --- Activity thresholds --------------------------------------------------
#: How far above its own quiet level a track must rise to count as playing.
ACTIVE_MARGIN_DB = 9.0

#: A hard floor, so a track recorded in a silent room cannot have its noise
#: promoted to "playing" just by being 9 dB above digital silence.
ABSOLUTE_FLOOR_DB = -48.0

#: Peak below which a whole track holds no audio at all — an automation or
#: folder track that recorded silence. Matches instrument_tagging.SILENCE_PEAK,
#: which is calibrated on the same kind of material.
DEAD_TRACK_PEAK_DB = -40.0

#: Tracks that must be active together before a moment counts as music, when no
#: rhythm track is playing.
MIN_ACTIVE_TRACKS = 3

# --- Take segmentation ----------------------------------------------------
#: Music must persist this long before a take opens, so a stray chord or a
#: drum-check does not start one.
ENTER_SECONDS = 2.5

#: Quiet must persist this long before a take closes. Songs contain rests,
#: breakdowns and dramatic pauses; this is what stops one becoming two takes.
EXIT_SECONDS = 6.0

#: Takes closer together than this are one take. A false start followed by an
#: immediate restart is musically two attempts, but they are so close that
#: splitting them reliably needs more than loudness.
MERGE_GAP_SECONDS = 4.0

#: Takes shorter than this are reported as fragments rather than songs — a
#: count-in that collapsed, or noodling between numbers. They are kept, because
#: a short false start is a version the band may want, but flagged so the
#: review UI can fold them away by default.
FRAGMENT_SECONDS = 20.0

#: Everything below this is dropped outright: too short to be even a false
#: start, and keeping them would bury the real takes.
MIN_TAKE_SECONDS = 8.0

#: Padding around a detected take, so a quiet count-in or a ringing final chord
#: is not clipped off.
PAD_HEAD_SECONDS = 1.5
PAD_TAIL_SECONDS = 2.5


def classify_track(name: str) -> str:
    """Map a Reaper track name onto a Demucs-style stem bucket."""
    lowered = name.lower()
    for pattern, role in _ROLE_PATTERNS:
        if re.search(pattern, lowered):
            return role
    return "other"


@dataclass
class Track:
    """One session track, positioned on the timeline with its envelope."""

    name: str
    source_name: str
    #: Timeline seconds at which this track's audio starts.
    position: float
    envelope: Envelope
    role: str = "other"

    def __post_init__(self) -> None:
        if self.role == "other":
            self.role = classify_track(self.name)

    @property
    def peak_db(self) -> float:
        if len(self.envelope) == 0:
            return float("-inf")
        return _db(float(np.max(self.envelope.peak)))

    @property
    def is_dead(self) -> bool:
        """Whether the track holds no audio worth scanning."""
        return bool(self.peak_db < DEAD_TRACK_PEAK_DB)

    def active_frames(self) -> np.ndarray:
        """Boolean per envelope frame: is this track playing?"""
        levels = _db_array(self.envelope.rms)
        finite = levels[np.isfinite(levels)]
        if finite.size == 0:
            return np.zeros(len(self.envelope), dtype=bool)
        # The 20th percentile is this track's own resting level — room tone plus
        # whatever bleeds in — which is what "playing" has to rise above.
        floor = float(np.percentile(finite, 20))
        threshold = max(floor + ACTIVE_MARGIN_DB, ABSOLUTE_FLOOR_DB)
        return levels > threshold


@dataclass
class Take:
    """A stretch of the timeline where the band was playing."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def is_fragment(self) -> bool:
        return self.duration < FRAGMENT_SECONDS


@dataclass
class Activity:
    """The timeline's music/not-music verdict, frame by frame."""

    playing: np.ndarray
    #: How many live tracks are active in each frame (diagnostics + tuning).
    active_count: np.ndarray
    start: float
    fps: int
    tracks: List[Track] = field(default_factory=list)


def build_activity(tracks: Sequence[Track], fps: int) -> Activity:
    """Combine every track's envelope into one music/not-music decision.

    Each track is laid onto a shared grid at its own ``position``, because
    tracks within one recording pass do not necessarily start together.
    """
    live = [track for track in tracks if not track.is_dead]
    if not live:
        return Activity(
            playing=np.zeros(0, dtype=bool),
            active_count=np.zeros(0, dtype=int),
            start=0.0,
            fps=fps,
            tracks=[],
        )

    start = min(track.position for track in live)
    end = max(track.position + track.envelope.duration for track in live)
    frames = int(np.ceil((end - start) * fps))

    active_count = np.zeros(frames, dtype=int)
    rhythm_active = np.zeros(frames, dtype=bool)

    for track in live:
        offset = int(round((track.position - start) * fps))
        flags = track.active_frames()
        stop = min(offset + len(flags), frames)
        if stop <= offset:
            continue
        window = flags[: stop - offset]
        active_count[offset:stop] += window
        if track.role in RHYTHM_ROLES:
            rhythm_active[offset:stop] |= window

    # A rhythm instrument playing is enough on its own; otherwise it takes
    # several tracks at once, which talking into one mic never produces.
    playing = rhythm_active | (active_count >= MIN_ACTIVE_TRACKS)

    return Activity(
        playing=playing,
        active_count=active_count,
        start=start,
        fps=fps,
        tracks=live,
    )


def detect_takes(activity: Activity) -> List[Take]:
    """Segment the activity signal into takes."""
    if activity.playing.size == 0:
        return []

    spans = _hysteresis_spans(
        activity.playing,
        enter_frames=int(ENTER_SECONDS * activity.fps),
        exit_frames=int(EXIT_SECONDS * activity.fps),
    )

    takes = [
        Take(
            start=activity.start + begin / activity.fps,
            end=activity.start + finish / activity.fps,
        )
        for begin, finish in spans
    ]
    takes = _merge_close(takes, MERGE_GAP_SECONDS)
    takes = _pad(takes, activity)
    return [take for take in takes if take.duration >= MIN_TAKE_SECONDS]


def _hysteresis_spans(
    playing: np.ndarray, enter_frames: int, exit_frames: int
) -> List[tuple[int, int]]:
    """Find spans of ``playing``, requiring sustained runs to switch state.

    Implemented over run-lengths rather than frame by frame: a take is open
    until a run of quiet long enough to be *between* songs, and only a run of
    music long enough to be a song can open one.
    """
    spans: List[tuple[int, int]] = []
    inside = False
    begin = 0
    for value, start, length in _runs(playing):
        if not inside and value and length >= enter_frames:
            inside = True
            begin = start
        elif inside and not value and length >= exit_frames:
            inside = False
            spans.append((begin, start))
    if inside:
        spans.append((begin, len(playing)))
    return spans


def _runs(values: np.ndarray):
    """Yield ``(value, start, length)`` for each run of equal values."""
    if values.size == 0:
        return
    change = np.flatnonzero(values[1:] != values[:-1]) + 1
    bounds = np.concatenate(([0], change, [values.size]))
    for start, stop in zip(bounds[:-1], bounds[1:]):
        yield bool(values[start]), int(start), int(stop - start)


def _merge_close(takes: List[Take], gap: float) -> List[Take]:
    merged: List[Take] = []
    for take in takes:
        if merged and take.start - merged[-1].end <= gap:
            merged[-1] = Take(merged[-1].start, take.end)
        else:
            merged.append(take)
    return merged


def _pad(takes: List[Take], activity: Activity) -> List[Take]:
    """Widen each take, without running into its neighbour or off the end."""
    limit = activity.start + len(activity.playing) / activity.fps
    padded: List[Take] = []
    for index, take in enumerate(takes):
        previous_end = padded[-1].end if padded else activity.start
        next_start = takes[index + 1].start if index + 1 < len(takes) else limit
        padded.append(
            Take(
                start=max(take.start - PAD_HEAD_SECONDS, previous_end),
                end=min(take.end + PAD_TAIL_SECONDS, next_start),
            )
        )
    return padded


def _db(value: float) -> float:
    """Linear amplitude to dBFS.

    Returns a plain ``float``, not a numpy scalar: these values are written
    straight to the database, and asyncpg rejects ``np.float64``/``np.bool_``
    where it wants a real or a boolean.
    """
    return float(20.0 * np.log10(value)) if value > 0 else float("-inf")


def _db_array(values: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(np.maximum(values, 1e-12))
