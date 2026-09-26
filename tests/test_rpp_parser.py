"""Tests for the Reaper project parser (src/production/rpp_parser.py).

The fixture below is trimmed from one of the band's real projects, keeping the
three things that broke naive parsing of it: the whole file is wrapped in one
<REAPER_PROJECT> chunk, a track's NAME is shadowed by the NAME of every item
and FX inside it, and one track's item starts later than its pass-mates.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production.rpp_parser import parse_project_text  # noqa: E402

PROJECT = """<REAPER_PROJECT 0.1 "7.39/macOS-arm64" 1780706838
  RIPPLE 0 0
  <TRACK {AAAA}
    NAME "4 Kev Vox"
    <FXCHAIN
      <VST "VST3: Pro-Q 3" name-that-must-not-win.vst3
        NAME "a plugin preset"
      >
    >
    <ITEM
      POSITION 100.5
      LENGTH 60.25
      NAME "07-4 Kev Vox-260501_2359.wv"
      SOFFS 0
      PLAYRATE 1 1 0 -1 0 0.0025
      RECPASS 4
      <SOURCE WAVPACK
        FILE "07-4 Kev Vox-260501_2359.wv"
      >
    >
    <ITEM
      POSITION 10
      LENGTH 5
      RECPASS 1
      <SOURCE WAVPACK
        FILE "/elsewhere/old project/07-4 Kev Vox-260313_2049.wv"
      >
    >
  >
  <TRACK {BBBB}
    NAME "3 Electric"
    <ITEM
      POSITION 145.5
      LENGTH 15
      RECPASS 4
      <SOURCE WAVPACK
        FILE "13-3 Electric-260502_0002.wv"
      >
    >
  >
  <TRACK {CCCC}
    NAME "Drums MIDI"
    <ITEM
      POSITION 100.5
      LENGTH 60.25
      RECPASS 4
      <SOURCE MIDI
        HASDATA 1 960 QN
      >
    >
  >
>
"""


def test_track_names_are_not_shadowed_by_nested_names():
    project = parse_project_text(PROJECT)

    assert project.track_names == ["4 Kev Vox", "3 Electric", "Drums MIDI"]


def test_audio_items_are_parsed_with_their_timeline_position():
    project = parse_project_text(PROJECT)
    item = next(i for i in project.items if i.rec_pass == 4 and i.track_name == "4 Kev Vox")

    assert item.position == 100.5
    assert item.length == 60.25
    assert item.end == 160.75
    assert item.start_offset == 0.0
    assert item.play_rate == 1.0
    assert item.source_type == "WAVPACK"
    assert item.source_name == "07-4 Kev Vox-260501_2359.wv"


def test_midi_items_are_skipped_because_they_have_no_audio_to_scan():
    project = parse_project_text(PROJECT)

    assert all(item.track_name != "Drums MIDI" for item in project.items)


def test_items_group_into_recording_passes_in_timeline_order():
    project = parse_project_text(PROJECT)
    passes = project.passes()

    assert [p.number for p in passes] == [1, 4]
    assert len(passes[1].items) == 2


def test_a_pass_spans_its_latest_starting_track():
    """A player who arms late shifts the pass's end, not its start."""
    project = parse_project_text(PROJECT)
    fourth = next(p for p in project.passes() if p.number == 4)

    assert fourth.start == 100.5
    assert fourth.end == 160.75
    assert fourth.duration == 60.25


def test_an_absolute_source_path_keeps_only_its_basename_for_matching():
    """Earlier passes point into other project folders; a zip holds basenames."""
    project = parse_project_text(PROJECT)
    old = next(i for i in project.items if i.rec_pass == 1)

    assert old.source_name == "07-4 Kev Vox-260313_2049.wv"


def test_a_file_that_is_not_a_project_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        parse_project_text("NOT 1\nA PROJECT 2\n")
