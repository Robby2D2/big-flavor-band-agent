"""Tests for splitting a region into attempts (src/production/session_attempts.py).

Every case here is one the band's own session produced. The two that matter most
pull in opposite directions, and telling them apart is the whole job:

* Two attempts at one song, separated by the band discussing it — and noodling
  right through the discussion, so loudness alone never sees a gap.
* One attempt at one song with people talking *over* an instrumental solo
  ("here comes a big solo"), which must not be split in half.

What separates them is whether the band actually stopped: measured on the real
session, note gaps inside the solo reached 1.0s, while the gap between the two
attempts was 5.7s.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.production.session_attempts import (  # noqa: E402
    CHATTER,
    LYRICS,
    MIN_STOP_SECONDS,
    Attempt,
    _parse_labels,
    attempts_for_regions,
    attempts_from_labels,
    label_lines,
    smooth_labels,
)
from src.production.session_detect import Activity, Take  # noqa: E402
from src.production.session_transcribe import TranscriptLine  # noqa: E402

FPS = 20


def line(start: float, end: float, text: str = "words") -> TranscriptLine:
    return TranscriptLine(start=start, end=end, text=text, confidence=0.9)


def activity(playing_spans, total: float, start: float = 0.0) -> Activity:
    """An Activity that is playing everywhere except the given quiet spans."""
    frames = int(total * FPS)
    playing = np.ones(frames, dtype=bool)
    for quiet_start, quiet_end in playing_spans:
        begin = int((quiet_start - start) * FPS)
        finish = int((quiet_end - start) * FPS)
        playing[begin:finish] = False
    return Activity(
        playing=playing,
        active_count=np.full(frames, 3, dtype=int),
        start=start,
        fps=FPS,
        tracks=[],
    )


# --- Label smoothing ------------------------------------------------------

def test_one_misread_line_inside_a_song_is_put_back():
    labels = [LYRICS, CHATTER, LYRICS, LYRICS]

    assert smooth_labels(labels) == [LYRICS] * 4


def test_a_real_discussion_survives_smoothing():
    labels = [LYRICS, CHATTER, CHATTER, LYRICS]

    assert smooth_labels(labels) == labels


def test_a_count_in_at_the_start_is_left_alone():
    """There is no lyric run before it for it to have been broken out of."""
    labels = [CHATTER, LYRICS, LYRICS]

    assert smooth_labels(labels) == labels


# --- Attempt spans --------------------------------------------------------

def test_two_attempts_separated_by_a_real_stop_are_split():
    region = Take(0, 300)
    lines = [
        line(10, 60, "swinging party down the line"),
        line(70, 130, "feels like you guys want to do it again"),
        line(140, 200, "swinging party down the line"),
    ]
    labels = [LYRICS, CHATTER, LYRICS]
    # The band stopped for 6s before starting again.
    signal = activity([(132, 138)], total=300)

    attempts = attempts_from_labels(region, lines, labels, activity=signal)

    assert len(attempts) == 2
    assert attempts[0].take.end <= attempts[1].take.start


def test_talking_over_a_solo_does_not_split_the_song():
    """The case that made loudness-plus-words necessary, from pass 3 of the
    band's own session: someone shouts over the guitar solo."""
    region = Take(0, 300)
    lines = [
        line(10, 55, "gardening at night"),
        line(60, 65, "here comes a big solo"),
        line(100, 160, "gardening at night"),
    ]
    labels = [LYRICS, CHATTER, LYRICS]
    # Only note-length gaps: the band never stopped.
    signal = activity([(80, 81)], total=300)

    attempts = attempts_from_labels(region, lines, labels, activity=signal)

    assert len(attempts) == 1
    assert attempts[0].take.start == pytest.approx(0, abs=11)
    assert attempts[0].take.end == pytest.approx(300, abs=1)


def test_a_joined_attempt_keeps_only_the_sung_words():
    region = Take(0, 300)
    lines = [
        line(10, 55, "gardening at night"),
        line(60, 65, "here comes a big solo"),
        line(100, 160, "we angled up to the garbage town"),
    ]
    labels = [LYRICS, CHATTER, LYRICS]
    signal = activity([], total=300)

    attempt = attempts_from_labels(region, lines, labels, activity=signal)[0]

    assert "big solo" not in attempt.text
    assert "gardening at night" in attempt.text
    assert "garbage town" in attempt.text


def test_a_gap_exactly_at_the_threshold_counts_as_a_stop():
    region = Take(0, 300)
    lines = [line(10, 60, "a song"), line(100, 160, "the same song again")]
    labels = [LYRICS, LYRICS]
    signal = activity([(70, 70 + MIN_STOP_SECONDS)], total=300)

    attempts = attempts_from_labels(region, lines, labels, activity=signal)

    assert len(attempts) == 2


def test_a_region_of_pure_chatter_yields_no_attempts():
    """Measured on the real session: a 2m43s stretch of "hello tv listeners"
    was promoted to a take by loudness alone."""
    region = Take(0, 160)
    lines = [
        line(10, 20, "yeah hello hello tv listeners"),
        line(40, 50, "it's all good it's all good"),
        line(80, 90, "you're feeling it it's all coming together"),
    ]
    labels = [CHATTER, CHATTER, CHATTER]

    attempts = attempts_from_labels(region, lines, labels, activity=activity([], 160))

    assert attempts == []


def test_a_region_with_no_words_at_all_is_kept_whole():
    """It could be an instrumental, and there is no evidence either way."""
    region = Take(0, 120)

    attempts = attempts_from_labels(region, [], [], activity=activity([], 120))

    assert len(attempts) == 1
    assert attempts[0].take == region
    assert attempts[0].text == ""


def test_an_attempt_reaches_back_over_its_intro_to_where_the_band_started():
    """The music between the talking and the first sung word is the intro."""
    region = Take(0, 300)
    lines = [line(10, 20, "all right here we go"), line(60, 200, "the song's words")]
    labels = [CHATTER, LYRICS]
    # The band was quiet until 30s, then played an intro before the singing.
    signal = activity([(0, 30)], total=300)

    attempt = attempts_from_labels(region, lines, labels, activity=signal)[0]

    assert attempt.take.start == pytest.approx(30, abs=1)


def test_without_an_activity_signal_the_region_stays_one_attempt():
    """A fallback, not a preference: with no loudness signal nothing can say
    whether the band ever stopped, and splitting on the talking alone is exactly
    the mistake that cuts a song at its solo."""
    region = Take(0, 300)
    lines = [line(10, 60, "a"), line(70, 80, "talking"), line(100, 200, "b")]
    labels = [LYRICS, CHATTER, LYRICS]

    attempts = attempts_from_labels(region, lines, labels, activity=None)

    assert len(attempts) == 1
    assert "talking" not in attempts[0].text


def test_an_attempt_too_short_to_be_a_take_is_dropped():
    region = Take(0, 300)
    lines = [line(10, 12, "one line")]
    labels = [LYRICS]
    signal = activity([(0, 9), (13, 300)], total=300)

    assert attempts_from_labels(region, lines, labels, activity=signal) == []


# --- Reading the model's reply --------------------------------------------

def test_labels_are_read_out_of_a_reply_with_prose_around_the_json():
    reply = 'Sure!\n{"labels": ["lyrics", "chatter", "LYRICS"]}\nHope that helps.'

    assert _parse_labels(reply, 3) == [LYRICS, CHATTER, LYRICS]


def test_a_short_reply_is_padded_rather_than_rejected():
    """The lines it did not reach are the ones we know least about, and calling
    them lyrics keeps their audio."""
    assert _parse_labels('{"labels": ["chatter"]}', 3) == [CHATTER, LYRICS, LYRICS]


def test_a_long_reply_is_truncated():
    reply = '{"labels": ["chatter", "chatter", "chatter", "chatter"]}'

    assert _parse_labels(reply, 2) == [CHATTER, CHATTER]


@pytest.mark.parametrize(
    "reply", ["no json here", "{}", '{"labels": "not a list"}', "{oops"]
)
def test_an_unreadable_reply_is_reported_as_unreadable(reply):
    assert _parse_labels(reply, 3) is None


# --- One labelling call per pass ------------------------------------------

class FakeLLM:
    """Records what it was asked, and replies with prepared labels."""

    def __init__(self, labels=None, raises=False):
        self.labels = labels or []
        self.raises = raises
        self.prompts = []

    async def generate_response(self, messages, system=None, **kwargs):
        if self.raises:
            raise RuntimeError("ollama is down")
        self.prompts.append(messages[0]["content"])
        import json

        return json.dumps({"labels": self.labels})


@pytest.mark.asyncio
async def test_the_whole_pass_is_labelled_in_one_call():
    """Judging a line as sung or spoken is comparative — "it's all good" reads
    like a hook alone and like talking beside the pass's real lyrics — so every
    region's lines go to the model together."""
    regions = [
        (Take(0, 100), [line(10, 60, "the song's words")]),
        (Take(200, 300), [line(210, 260, "it's all good it's all good")]),
    ]
    llm = FakeLLM(labels=[LYRICS, CHATTER])

    per_region = await attempts_for_regions(regions, llm, activity=activity([], 300))

    assert len(llm.prompts) == 1
    assert "the song's words" in llm.prompts[0]
    assert "it's all good" in llm.prompts[0]
    assert len(per_region[0]) == 1
    assert per_region[1] == []


@pytest.mark.asyncio
async def test_labels_are_handed_back_to_the_region_they_came_from():
    regions = [
        (Take(0, 100), [line(10, 60, "a"), line(65, 90, "b")]),
        (Take(200, 300), [line(210, 260, "c")]),
    ]
    llm = FakeLLM(labels=[CHATTER, LYRICS, LYRICS])

    per_region = await attempts_for_regions(regions, llm, activity=activity([], 300))

    assert [a.text for a in per_region[0]] == ["b"]
    assert [a.text for a in per_region[1]] == ["c"]


@pytest.mark.asyncio
async def test_smoothing_does_not_reach_across_a_region_boundary():
    """Lines either side of a boundary are minutes apart, so a lone chatter line
    at the edge is not surrounded by the singing that follows it in the list."""
    regions = [
        (Take(0, 100), [line(10, 60, "a"), line(65, 90, "talking")]),
        (Take(200, 300), [line(210, 260, "c")]),
    ]
    llm = FakeLLM(labels=[LYRICS, CHATTER, LYRICS])

    per_region = await attempts_for_regions(regions, llm, activity=activity([], 300))

    assert [a.text for a in per_region[0]] == ["a"]


@pytest.mark.asyncio
async def test_an_llm_failure_leaves_every_region_whole():
    """A region nobody could label is a region a human splits, not a lost take."""
    lines = [line(10, 60, "a"), line(65, 90, "b")]
    llm = FakeLLM(raises=True)

    labels = await label_lines(lines, llm)

    assert labels == [LYRICS, LYRICS]


@pytest.mark.asyncio
async def test_lines_are_labelled_in_batches_rather_than_all_at_once():
    """Measured: an 86-line list degraded the local model badly, while a single
    short region gave it nothing to compare against."""
    from src.production.session_attempts import LABEL_BATCH

    lines = [line(i * 10, i * 10 + 5, f"line {i}") for i in range(LABEL_BATCH * 2 + 3)]
    llm = FakeLLM(labels=[LYRICS] * LABEL_BATCH)

    labels = await label_lines(lines, llm)

    assert len(llm.prompts) == 3
    assert len(labels) == len(lines)
