"""Tests for grouping a session's takes by song (src/production/session_grouping.py).

The cases are the ones the band's own session produced, as the owner read it on
issue #109: takes 8 and 9 are both "So Tired" and belong in one card, while take 7
transitions between two songs and belongs to neither.

What the module must never do matters as much: it must not group a take that has
no words to judge, and it must not lose one. A take missing from the output is
recorded material a producer can no longer see (SESS-14).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production.session_grouping import (  # noqa: E402
    MIN_DISTINCTIVE_WORDS,
    START_ATTEMPT_GAP_SECONDS,
    distinctive_words,
    group_takes,
    overlap,
    split_counts,
    ungrouped_ids,
)

SO_TIRED_FULL = (
    "so tired of waiting for the morning light to fall across the kitchen floor "
    "so tired of counting every reason that i should not walk out the door"
)
SO_TIRED_RESTART = "so tired of waiting for the morning light"
GARDENING = (
    "gardening at night is never where i want to be and the fences are all down "
    "again so we planted rows of copper wire beneath the porch"
)


def take(
    take_id: int,
    transcript: str | None,
    start: float | None = None,
    end: float | None = None,
) -> dict:
    """One take row. Times default far apart, so only the words are in play."""
    start = take_id * 1000.0 if start is None else start
    return {
        "id": take_id,
        "transcript": transcript,
        "start_seconds": start,
        "end_seconds": start + 100.0 if end is None else end,
    }


def test_two_attempts_at_one_song_group_together():
    groups = group_takes([take(8, SO_TIRED_FULL), take(9, SO_TIRED_FULL)])

    assert groups == [[8, 9]]


def test_a_short_restart_groups_with_the_full_attempt():
    """A false start is a handful of words; containment is what still sees it."""
    groups = group_takes([take(1, SO_TIRED_RESTART), take(2, SO_TIRED_FULL)])

    assert groups == [[1, 2]]


def test_two_different_songs_stay_apart():
    groups = group_takes([take(1, SO_TIRED_FULL), take(2, GARDENING)])

    assert groups == []


def test_three_attempts_at_one_song_land_in_one_group():
    """Attempts start where the song starts, so they all share its opening."""
    groups = group_takes(
        [
            take(1, SO_TIRED_RESTART),
            take(2, SO_TIRED_FULL),
            take(3, "so tired of waiting for the morning light to fall"),
        ]
    )

    assert groups == [[1, 2, 3]]


def test_a_take_spanning_two_songs_is_left_on_its_own():
    """The transitional take (the owner's take 7) belongs to neither song."""
    takes = [
        take(7, f"{GARDENING} {SO_TIRED_FULL}"),
        take(8, SO_TIRED_FULL),
        take(9, SO_TIRED_FULL),
        take(6, GARDENING),
    ]

    groups = group_takes(takes)

    assert [8, 9] in groups
    assert all(7 not in ids for ids in groups)
    assert 7 in ungrouped_ids(takes, groups)


def test_a_wordless_take_is_never_grouped():
    takes = [take(1, None), take(2, ""), take(3, SO_TIRED_FULL), take(4, SO_TIRED_FULL)]

    groups = group_takes(takes)

    assert groups == [[3, 4]]
    assert ungrouped_ids(takes, groups) == [1, 2]


def test_chatter_does_not_group_on_common_words():
    """Two stretches of talking share filler, which is not evidence of a song."""
    groups = group_takes(
        [
            take(1, "okay so what do you want to do now i mean it is up to you"),
            take(2, "well i think we should just go and get it over with tonight"),
        ]
    )

    assert groups == []


def test_a_full_take_bridging_two_disjoint_attempts_is_left_alone():
    """The known ceiling, asserted so it stays a choice rather than a surprise.

    A full attempt whose two partners overlap only *it* is structurally identical
    to a stretch transitioning between two songs, so the shy answer wins: the
    bridge stands alone. Real attempts start where the song starts and share its
    opening, which is why this is the rare shape rather than the normal one.
    """
    groups = group_takes(
        [
            take(1, "so tired of waiting for the morning light"),
            take(2, SO_TIRED_FULL),
            take(3, "counting every single reason that i should not walk out the door"),
        ]
    )

    assert groups == []


def test_a_wordless_start_attempt_joins_the_song_that_follows_it():
    """The owner's takes 8 and 9, at the real session's own timings.

    Take 8 is 69 seconds of the band starting the song with nothing sung, so no
    comparison of words can ever place it — only the fact that the full attempt
    began 35 seconds later.
    """
    takes = [
        take(8, "you're feeling it it's all coming together", 14743, 14812),
        take(9, SO_TIRED_FULL, 14847, 15358),
    ]

    assert group_takes(takes) == [[8, 9]]


def test_a_stop_too_long_to_be_a_restart_leaves_the_take_alone():
    takes = [
        take(8, "it's all good it's all good", 14000, 14100),
        take(9, SO_TIRED_FULL, 14100 + START_ATTEMPT_GAP_SECONDS + 1, 14700),
    ]

    assert group_takes(takes) == []


def test_only_the_take_directly_before_a_song_attaches():
    """A run of chatter cannot ride in behind a start attempt."""
    takes = [
        take(6, "yeah hello hello tv listeners", 14676, 14697),
        take(7, "it's all good it's all good", 14702, 14737),
        take(8, "you're feeling it it's all coming together", 14743, 14812),
        take(9, SO_TIRED_FULL, 14847, 15358),
    ]

    groups = group_takes(takes)

    assert groups == [[8, 9]]
    assert ungrouped_ids(takes, groups) == [6, 7]


def test_a_take_with_its_own_words_is_never_grouped_by_proximity():
    takes = [
        take(1, GARDENING, 0, 100),
        take(2, SO_TIRED_FULL, 110, 600),
    ]

    assert group_takes(takes) == []


def test_no_take_is_lost_or_duplicated():
    takes = [
        take(1, SO_TIRED_FULL),
        take(2, SO_TIRED_RESTART),
        take(3, GARDENING),
        take(4, None),
        take(5, f"{GARDENING} {SO_TIRED_FULL}"),
    ]

    groups = group_takes(takes)
    grouped = [take_id for ids in groups for take_id in ids]

    assert len(grouped) == len(set(grouped)), "a take is in at most one group"
    in_groups, alone = split_counts(takes, groups)
    assert in_groups + alone == len(takes)
    assert sorted(grouped + ungrouped_ids(takes, groups)) == [1, 2, 3, 4, 5]


def test_grouping_does_not_depend_on_row_order():
    takes = [take(1, SO_TIRED_FULL), take(2, SO_TIRED_RESTART), take(3, GARDENING)]

    forward = group_takes(takes)
    backward = group_takes(list(reversed(takes)))

    assert [sorted(ids) for ids in forward] == [sorted(ids) for ids in backward]


def test_distinctive_words_drops_filler_and_short_words():
    words = distinctive_words("Oh, so tired of WAITING -- la la la!")

    assert "waiting" in words
    assert "tired" in words
    assert "so" not in words, "a stopword says nothing about which song this is"
    assert "la" not in words, "a syllable is not a word"


def test_overlap_measures_the_smaller_vocabulary():
    assert overlap(set(), {"tired"}) == 0.0
    assert overlap({"tired", "waiting"}, {"tired", "waiting", "morning", "floor"}) == 1.0
    assert MIN_DISTINCTIVE_WORDS >= 1
