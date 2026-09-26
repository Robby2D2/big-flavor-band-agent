"""Tests for take detection (src/production/session_detect.py).

Envelopes are synthesized rather than decoded from audio: the detector's input
*is* a loudness curve, so a curve built by hand tests it exactly, and the suite
stays runnable without ffmpeg or multi-gigabyte fixtures.

The cases are the ones the band's own sessions produce — talking between songs,
a rest in the middle of one, a false start, and a room where every mic hears
every instrument.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production.session_detect import (  # noqa: E402
    EXIT_SECONDS,
    FRAGMENT_SECONDS,
    MIN_TAKE_SECONDS,
    Track,
    build_activity,
    classify_track,
    detect_takes,
)
from src.production.wavpack_io import Envelope  # noqa: E402

FPS = 20


def envelope(*, seconds: float, level: float, fps: int = FPS) -> Envelope:
    """A flat envelope at one level."""
    frames = int(seconds * fps)
    values = np.full(frames, level, dtype=np.float32)
    return Envelope(rms=values, peak=values.copy(), fps=fps)


def envelope_from(spans, fps: int = FPS) -> Envelope:
    """Build an envelope from ``(seconds, level)`` spans laid end to end."""
    parts = [np.full(int(s * fps), level, dtype=np.float32) for s, level in spans]
    values = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
    return Envelope(rms=values, peak=values.copy(), fps=fps)


QUIET = 0.001   # room tone, about -60 dBFS
LOUD = 0.3      # a band playing


def track(name, spans, position=0.0, role=None):
    made = Track(
        name=name,
        source_name=f"{name}.wv",
        position=position,
        envelope=envelope_from(spans),
    )
    if role:
        made.role = role
    return made


# --- Track classification -------------------------------------------------

@pytest.mark.parametrize(
    "name,expected",
    [
        ("4 Kev Vox", "vocals"),
        ("8 Tom Vox", "vocals"),
        ("7 DRUM Mic", "drums"),
        ("Drums in stereo", "drums"),
        ("2 Bass", "bass"),
        ("6 ac g pickup", "guitar"),
        ("3 Electric", "guitar"),
        ("1 KEYS Mic", "piano"),
        ("Keys Serum Ch 1", "piano"),
        ("Room", "other"),
    ],
)
def test_track_names_map_to_stem_buckets(name, expected):
    assert classify_track(name) == expected


def test_a_band_member_called_tom_is_not_a_drum():
    """`tom` is a person here; only the drum spellings may claim the name."""
    assert classify_track("5 Tom Instr (bass too high)") != "drums"
    assert classify_track("8 Tom Vox") == "vocals"
    assert classify_track("Floor Tom") == "drums"


# --- Dead tracks ----------------------------------------------------------

def test_a_silent_automation_track_is_dead():
    silent = track("Key VOLUME", [(60, 0.0)])

    assert silent.is_dead


def test_a_quiet_room_mic_is_alive():
    """Measured at -34 dBFS peak on a real session; it must survive the cut."""
    room = track("1 KEYS Mic", [(60, 0.02)])

    assert not room.is_dead


def test_dead_tracks_do_not_contribute_activity():
    tracks = [
        track("Kev Vox", [(30, QUIET), (30, LOUD)]),
        track("Bass", [(30, QUIET), (30, LOUD)], role="bass"),
        track("Key VOLUME", [(60, 0.0)]),
    ]

    activity = build_activity(tracks, fps=FPS)

    assert [t.name for t in activity.tracks] == ["Kev Vox", "Bass"]


# --- Take detection -------------------------------------------------------

def test_one_song_between_two_silences_is_one_take():
    tracks = [
        track("Bass", [(30, QUIET), (120, LOUD), (30, QUIET)], role="bass"),
        track("Vox", [(30, QUIET), (120, LOUD), (30, QUIET)]),
    ]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert len(takes) == 1
    assert takes[0].start == pytest.approx(30, abs=2)
    assert takes[0].end == pytest.approx(150, abs=3)


def test_two_songs_separated_by_talking_are_two_takes():
    gap = EXIT_SECONDS + 10
    spans = [(20, QUIET), (100, LOUD), (gap, QUIET), (100, LOUD), (20, QUIET)]
    tracks = [track("Bass", spans, role="bass"), track("Vox", spans)]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert len(takes) == 2


def test_a_rest_inside_a_song_does_not_split_it():
    """Songs contain pauses; only a between-songs silence ends a take."""
    rest = EXIT_SECONDS - 2
    spans = [(20, QUIET), (60, LOUD), (rest, QUIET), (60, LOUD), (20, QUIET)]
    tracks = [track("Bass", spans, role="bass"), track("Vox", spans)]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert len(takes) == 1


def test_a_short_false_start_is_kept_and_flagged_as_a_fragment():
    """A collapsed intro is a version the band may want, not noise to discard."""
    gap = EXIT_SECONDS + 10
    false_start = FRAGMENT_SECONDS - 5
    spans = [
        (20, QUIET), (false_start, LOUD), (gap, QUIET), (120, LOUD), (20, QUIET),
    ]
    tracks = [track("Bass", spans, role="bass"), track("Vox", spans)]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert len(takes) == 2
    assert takes[0].is_fragment
    assert not takes[1].is_fragment


def test_a_moment_of_noise_is_too_short_to_be_a_take():
    spans = [(30, QUIET), (MIN_TAKE_SECONDS - 5, LOUD), (30, QUIET)]
    tracks = [track("Bass", spans, role="bass"), track("Vox", spans)]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert takes == []


def test_one_person_talking_into_one_mic_is_not_a_take():
    """The case the whole activity rule exists for."""
    tracks = [
        track("Kev Vox", [(20, QUIET), (120, LOUD), (20, QUIET)]),
        track("Tom Vox", [(160, QUIET)]),
        track("Guitar", [(160, QUIET)], role="guitar"),
        track("Keys", [(160, QUIET)], role="piano"),
    ]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert takes == []


def test_a_rhythm_track_alone_is_enough_to_be_music():
    """Drums playing is a song starting, whatever else is quiet."""
    tracks = [
        track("Drums", [(20, QUIET), (120, LOUD), (20, QUIET)], role="drums"),
        track("Kev Vox", [(160, QUIET)]),
        track("Guitar", [(160, QUIET)], role="guitar"),
    ]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    assert len(takes) == 1


def test_tracks_are_aligned_by_their_timeline_position():
    """A guitarist who arms late is offset by minutes; ignoring that would put
    their audio — and any take boundary drawn from it — out of sync."""
    # The early track holds steady room tone: loud enough to be a live track,
    # never rising above its own resting level, so it anchors the grid at 0
    # without ever counting as playing.
    late = track(
        "Drums", [(10, QUIET), (60, LOUD), (10, QUIET)], position=100.0, role="drums"
    )
    early = track("Kev Vox", [(160, 0.05)], position=0.0)

    activity = build_activity([late, early], fps=FPS)
    takes = detect_takes(activity)

    # The grid is anchored at the earliest track, and the drums' music lands
    # 110s along it — its own 100s position plus the 10s of quiet it opens with.
    assert activity.start == 0.0
    assert len(takes) == 1
    assert takes[0].start == pytest.approx(110, abs=3)


def test_adjacent_takes_do_not_overlap_after_padding():
    gap = EXIT_SECONDS + 1
    spans = [(20, QUIET), (60, LOUD), (gap, QUIET), (60, LOUD), (20, QUIET)]
    tracks = [track("Bass", spans, role="bass"), track("Vox", spans)]

    takes = detect_takes(build_activity(tracks, fps=FPS))

    for earlier, later in zip(takes, takes[1:]):
        assert earlier.end <= later.start


def test_a_pass_with_no_live_tracks_yields_nothing():
    takes = detect_takes(build_activity([track("Key VOLUME", [(60, 0.0)])], fps=FPS))

    assert takes == []


def test_measurements_are_plain_python_numbers_not_numpy_scalars():
    """These go straight into the database, and asyncpg refuses np.float64 /
    np.bool_ where a real or a boolean is expected — which failed a real scan."""
    alive = track("Kev Vox", [(30, QUIET), (30, LOUD)])
    silent = track("Key VOLUME", [(60, 0.0)])

    assert type(alive.peak_db) is float
    assert type(alive.is_dead) is bool
    assert type(silent.peak_db) is float
    assert type(silent.is_dead) is bool
