"""Which of a session's takes are attempts at the same song.

A scan produces takes, not songs. The band plays a song two or three times —
often a start that breaks down, then a real go — and every attempt arrives as its
own stretch with no identity, so review reads as strangers.

What two attempts share is **words**, so this is a comparison of transcripts, and
deliberately nothing else:

* **No catalog match.** The owner asked for a guess, not a lookup, and a
  rehearsal take is half-mumbled — matching it against 1,300 titles would assert
  a song identity the audio does not support.
* **No model call.** Every span decision in this pipeline is arithmetic in Python
  for the reason ``session_attempts`` documents: asked to reason about spans, the
  local 14B invents. Counting shared words cannot.
* **No acoustic measurement.** Rhythm was already measured as a refiner for
  detection and scored *talking* above the song.

Measured on the band's own "May the Farts Be With You" session (9 takes), which
is where every threshold below comes from:

1. **Containment, not Jaccard.** A restart is eight words against a full take's
   sixty; ``shared / min(words)`` sees that the short one is inside the long one,
   while Jaccard would score it 0.13 and never group the restarts the band makes
   most. The session's two attempts at "Swinging Party" (takes 2 and 3) score
   **0.93** this way, and no unrelated pair in the session reaches 0.30.
2. **A pair also needs enough shared words to mean anything.** Ratios lie at
   small sizes: a three-word stretch of chatter sharing two words scores 0.67
   without being evidence of anything.
3. **A take that matches two takes which do not match each other is left alone.**
   That is the shape of a stretch played while moving between songs: it contains
   both, so it matches attempts at either while those have nothing in common. It
   is evidence of *two* songs, so it is not confident evidence of one (SESS-14).
   This is also what stops such a take from swallowing both songs into one group
   — containment likes it best of all, its words containing everyone else's.
4. **What is left groups by transitive closure, and every group is a clique**,
   since rule 3 has already removed any take bridging two members that disagree.
5. **A start attempt has no words yet, so words cannot place it.** The session's
   take 8 is 69 seconds of the band starting "So Tired" with nothing sung, then a
   35-second stop, then take 9 — the full attempt. The owner reads those two as
   one song, and no amount of vocabulary will ever say so. So a take too
   wordless to judge is attached to the take that *immediately* follows it when
   that one has words and starts within ``START_ATTEMPT_GAP_SECONDS``. Only the
   immediately preceding take, and only when it is itself wordless, so several
   stretches of chatter cannot chain in (the same session's takes 5, 6 and 7 sit
   89s, 62s and 4.5s apart and stay on their own) and a take with words of its
   own is never placed by proximity.

Rule 3 is the ceiling on what any of this can know: a full attempt bridging two
partial ones looks exactly like a transition between two songs. The shy answer
wins, because a wrong group costs a producer more than no group. Nothing here is
presented as settled — the name is offered for correction and any take can be
separated out by hand (SESS-05).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set, Tuple

#: Words too common to say anything about which song a take is. Deliberately
#: short — this is stopword removal, not vocabulary curation, and a real lyric
#: word that survives is harmless while a missing one only makes the guess shyer.
STOPWORDS = frozenset(
    """
    a about all am an and are as at be been but by can cant come could did do
    dont for from get go going got had has have he her here hes him his how i
    id if ill im in is it its ive just know let like me my no not now of oh off
    on one or our out over said she should so some that thats the their them
    then there these they this to too up us very was we well were what when
    where which who will with would yeah yes you your youre
    """.split()
)

#: A word needs this many characters to count. "oh", "la" and stray syllables are
#: what a band sings while finding the song, not what identifies it.
MIN_WORD_LENGTH = 3

#: Below this many distinctive words a take is not evidence of a song, so words
#: cannot group it. A wordless take lands here by definition.
MIN_DISTINCTIVE_WORDS = 4

#: How much of the shorter take's vocabulary must appear in the longer one's.
SAME_SONG_OVERLAP = 0.6

#: And how many words that must be, so a ratio over a handful of words cannot
#: carry a match on its own.
MIN_SHARED_WORDS = 3

#: How long after a wordless take a sung take may begin and still be the same
#: song. Measured: the start attempt that motivated this (take 8) stopped 35.4s
#: before the full attempt, while the chatter stretches before it sat 62s and 89s
#: from their neighbours.
START_ATTEMPT_GAP_SECONDS = 45.0

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def distinctive_words(transcript: str | None) -> Set[str]:
    """The words of a take that say something about which song it is."""
    if not transcript:
        return set()
    return {
        word
        for word in (match.group(0).lower() for match in _WORD.finditer(transcript))
        if len(word) >= MIN_WORD_LENGTH and word not in STOPWORDS
    }


def overlap(left: Set[str], right: Set[str]) -> float:
    """How much of the smaller vocabulary the two takes share, 0.0-1.0."""
    smaller = min(len(left), len(right))
    if smaller == 0:
        return 0.0
    return len(left & right) / smaller


def same_song(left: Set[str], right: Set[str]) -> bool:
    """Whether two takes' words say they are attempts at one song."""
    return (
        len(left & right) >= MIN_SHARED_WORDS
        and overlap(left, right) >= SAME_SONG_OVERLAP
    )


def group_takes(takes: Sequence[Mapping[str, Any]]) -> List[List[int]]:
    """Group a session's takes by the song they appear to be attempts at.

    ``takes`` are rows in timeline order, each carrying ``id``, ``transcript``,
    ``start_seconds`` and ``end_seconds``. Returns one list of take ids per
    group, ordered by the group's first take, and **only** for groups of two or
    more: a take on its own needs no group, and every take not named here stays
    visible by itself (SESS-14).
    """
    order = {row["id"]: index for index, row in enumerate(takes)}
    words: Dict[int, Set[str]] = {
        row["id"]: distinctive_words(row.get("transcript")) for row in takes
    }
    sung = [
        row["id"] for row in takes if len(words[row["id"]]) >= MIN_DISTINCTIVE_WORDS
    ]

    partners = {
        take_id: {
            other
            for other in sung
            if other != take_id and same_song(words[take_id], words[other])
        }
        for take_id in sung
    }
    confident = [
        take_id for take_id in sung if not _straddles(take_id, partners, words)
    ]

    groups = {
        component[0]: component for component in _components(confident, partners)
    }
    _attach_start_attempts(takes, set(sung), groups, order)

    grouped = [
        sorted(ids, key=lambda take_id: order[take_id])
        for ids in groups.values()
        if len(ids) > 1
    ]
    return sorted(grouped, key=lambda ids: order[ids[0]])


def _straddles(
    take_id: int, partners: Dict[int, Set[int]], words: Dict[int, Set[str]]
) -> bool:
    """Whether a take matches two takes that do not match each other.

    Evidence of two songs is not confident evidence of one, so such a take is
    left standing alone rather than folded into either (SESS-14).
    """
    return any(
        not same_song(words[left], words[right])
        for left in partners[take_id]
        for right in partners[take_id]
        if left < right
    )


def _components(
    take_ids: Sequence[int], partners: Dict[int, Set[int]]
) -> List[List[int]]:
    """Connected groups of takes whose words match.

    Every component is a clique: a take bridging two members that disagree has
    already been pulled out by ``_straddles``, so nothing can chain A-B-C into a
    group whose ends have nothing in common.
    """
    remaining = set(take_ids)
    components: List[List[int]] = []
    while remaining:
        frontier = [min(remaining)]
        remaining.discard(frontier[0])
        component = list(frontier)
        while frontier:
            current = frontier.pop()
            for neighbour in sorted(partners[current] & remaining):
                remaining.discard(neighbour)
                component.append(neighbour)
                frontier.append(neighbour)
        components.append(component)
    return components


def _attach_start_attempts(
    takes: Sequence[Mapping[str, Any]],
    sung: Set[int],
    groups: Dict[int, List[int]],
    order: Dict[int, int],
) -> None:
    """Put a wordless start attempt with the song it was an attempt at.

    A take that broke down before anybody sang has nothing for words to match, so
    the only thing that places it is what came *immediately* after: the band
    cannot start a song again without stopping first. Attaching only the directly
    preceding take, and only when it has no words of its own, keeps a run of
    chatter from riding along behind it.
    """
    group_of = {take_id: key for key, ids in groups.items() for take_id in ids}

    for index, row in enumerate(takes):
        if index == 0 or row["id"] not in sung:
            continue
        candidate = takes[index - 1]
        if candidate["id"] in sung or candidate["id"] in group_of:
            continue
        gap = (row.get("start_seconds") or 0.0) - (candidate.get("end_seconds") or 0.0)
        if gap > START_ATTEMPT_GAP_SECONDS:
            continue

        key = group_of.get(row["id"])
        if key is None:
            key = row["id"]
            groups[key] = [row["id"]]
            group_of[row["id"]] = key
        groups[key].append(candidate["id"])
        group_of[candidate["id"]] = key

    for ids in groups.values():
        ids.sort(key=lambda take_id: order[take_id])


def ungrouped_ids(
    takes: Sequence[Mapping[str, Any]], groups: Iterable[Sequence[int]]
) -> List[int]:
    """The takes no group claimed — every one of which stays visible (SESS-14)."""
    claimed = {take_id for ids in groups for take_id in ids}
    return [row["id"] for row in takes if row["id"] not in claimed]


def split_counts(
    takes: Sequence[Mapping[str, Any]], groups: Sequence[Sequence[int]]
) -> Tuple[int, int]:
    """``(takes in groups, takes on their own)`` — they must sum to ``len(takes)``."""
    in_groups = sum(len(ids) for ids in groups)
    return in_groups, len(takes) - in_groups
