"""Who may remove a queued song, and how the queue remembers who added it (issue #102).

A listener may remove a queued song they added themselves but nobody else's
(ACCT-05, ACCT-15), so removal cannot be authorized on role rank alone — the queue
has to carry an adder and the decision has to compare it against the caller.

These tests pin the *properties* that matter rather than a particular payload shape:

- an unidentified caller or an unattributed song is a refusal, never a match
  (ACCT-04) — this is the half that silently turns into "anyone may remove anything"
  if the comparison is written as `song.get("added_by") == caller.user_id`, because
  None == None;
- attribution survives the JSONB round-trip the radio state store does, which *is*
  the persistence mechanism (RAD-04, RAD-13);
- the adder's account id never leaves the backend — the page is told whether the
  entry is its reader's, not whose it is.

No DB, no LLM, no stream: these are pure functions over a state dict.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.radio_service import (  # noqa: E402
    ADDED_BY,
    attribute_queue_entry,
    may_remove_from_queue,
    queue_entry_for_display,
)
from src.auth import Caller  # noqa: E402

ALICE = "google-sub-alice"
BOB = "google-sub-bob"


def _song(song_id=1, adder=None):
    song = {"id": song_id, "title": f"Song {song_id}", "duration": 180}
    if adder is not None:
        song[ADDED_BY] = adder
    return song


def _caller(role="listener", user_id=ALICE):
    return Caller(role=role, user_id=user_id)


# --- Attribution ----------------------------------------------------------

def test_adding_stamps_the_adder():
    song = attribute_queue_entry(_song(), ALICE)
    assert song[ADDED_BY] == ALICE


def test_adding_without_an_identified_caller_leaves_the_song_unattributed():
    song = attribute_queue_entry(_song(), None)
    assert ADDED_BY not in song


def test_attribution_survives_the_json_round_trip_the_store_does():
    # The queue lives inside the radio_state JSONB column, so this round trip is
    # exactly how the attribution outlives a backend restart (RAD-04, RAD-13).
    state = {"queue": [attribute_queue_entry(_song(7), ALICE)], "current_song": None}

    restored = json.loads(json.dumps(state))

    assert restored["queue"][0][ADDED_BY] == ALICE
    assert may_remove_from_queue(restored["queue"][0], _caller(user_id=ALICE))


# --- Who may remove -------------------------------------------------------

def test_editor_may_remove_a_song_somebody_else_added():
    assert may_remove_from_queue(_song(adder=ALICE), _caller("editor", BOB))


def test_admin_may_remove_a_song_somebody_else_added():
    assert may_remove_from_queue(_song(adder=ALICE), _caller("admin", BOB))


def test_editor_may_remove_an_unattributed_song():
    assert may_remove_from_queue(_song(), _caller("editor", BOB))


def test_listener_may_remove_their_own_addition():
    assert may_remove_from_queue(_song(adder=ALICE), _caller("listener", ALICE))


def test_listener_may_not_remove_somebody_elses_addition():
    assert not may_remove_from_queue(_song(adder=BOB), _caller("listener", ALICE))


def test_an_unattributed_song_is_nobody_s_own():
    # RAD-13: everything queued before attribution existed, topped up automatically,
    # or asked for through the DJ lands here, and is editor-only.
    assert not may_remove_from_queue(_song(), _caller("listener", ALICE))


def test_two_unknowns_are_not_a_match():
    # The trap this is here to keep closed: comparing a missing adder against a
    # missing caller id is equality in Python, and would hand every listener every
    # unattributed song (ACCT-04).
    assert not may_remove_from_queue(_song(), _caller("listener", None))


def test_an_identified_listener_against_an_unknown_role_is_refused():
    # An unreadable role must not fall through to "editor" (ACCT-04).
    assert not may_remove_from_queue(_song(adder=BOB), _caller("superuser", ALICE))


def test_an_unidentified_caller_cannot_remove_an_attributed_song():
    assert not may_remove_from_queue(_song(adder=ALICE), _caller("listener", None))


# --- What the page is told ------------------------------------------------

def test_display_entry_never_carries_the_adder_id():
    entry = queue_entry_for_display(_song(adder=BOB), _caller("listener", ALICE))
    assert ADDED_BY not in entry
    assert BOB not in json.dumps(entry)


def test_display_entry_marks_the_readers_own_addition():
    entry = queue_entry_for_display(_song(adder=ALICE), _caller("listener", ALICE))
    assert entry["added_by_me"] is True


def test_display_entry_does_not_mark_somebody_elses_addition():
    entry = queue_entry_for_display(_song(adder=BOB), _caller("listener", ALICE))
    assert entry["added_by_me"] is False


def test_display_entry_does_not_mark_an_unattributed_song():
    entry = queue_entry_for_display(_song(), _caller("listener", ALICE))
    assert entry["added_by_me"] is False


def test_display_entry_keeps_the_fields_the_page_renders():
    entry = queue_entry_for_display(_song(5, adder=ALICE), _caller("listener", ALICE))
    assert entry["id"] == 5
    assert entry["title"] == "Song 5"
    assert entry["duration"] == 180


def test_display_projection_leaves_the_stored_entry_alone():
    song = _song(adder=ALICE)
    queue_entry_for_display(song, _caller("listener", ALICE))
    assert song[ADDED_BY] == ALICE


def test_no_current_song_stays_none():
    assert queue_entry_for_display(None, _caller()) is None
