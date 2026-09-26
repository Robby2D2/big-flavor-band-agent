"""The air chain in streaming/radio.liq keeps catalog music reachable (issue #104).

This bug was a config *shape*, not a line of logic: `mksafe` was applied to each
child of the air fallback, and `mksafe` makes a source always ready, so the first
child always won and the catalog fallback source could never be selected. An empty
queue therefore served `mksafe`'s own silence -- measured on the live stack, Icecast
then dropped the source on its socket timeout and /stream 404'd until Liquidsoap was
restarted. RAD-02 ("MUST NOT fall to silence while there are playable songs") was
unmet for as long as the shape stood.

So the shape is what these tests pin, because the shape is what regressed and what
a well-meaning change would restore: `AGENTS.md` asked for `mksafe()`-wrapped
playlist sources for years, which is exactly how the children came to be wrapped.
They are not a substitute for listening to the stream -- that verification is in the
PR -- they are the guard that the file cannot drift back.
"""
import re
from pathlib import Path

import pytest

RADIO_LIQ = Path(__file__).resolve().parents[1] / "streaming" / "radio.liq"


@pytest.fixture(scope="module")
def code():
    """radio.liq with comments and blank lines stripped, so prose cannot satisfy a test."""
    lines = []
    for line in RADIO_LIQ.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return "\n".join(lines)


@pytest.fixture(scope="module")
def air_chain(code):
    """The single statement that assembles the air source from its children."""
    matches = [line for line in code.splitlines() if re.match(r"^radio\s*=\s*mksafe\(", line)]
    assert len(matches) == 1, f"expected exactly one mksafe'd air chain, found {matches}"
    return matches[0]


def test_the_air_chain_is_made_safe_once_around_the_fallback(air_chain):
    """mksafe wraps the *result*, which is what keeps the children able to yield."""
    assert re.match(r"^radio\s*=\s*mksafe\(\s*fallback\(", air_chain), air_chain


def test_no_source_is_made_safe_before_the_fallback_chooses(code):
    """An mksafe'd child is always ready, so nothing after it can ever be selected.

    This is the defect itself: `mksafe(radio_queue)` as a child made the catalog
    source dead code.
    """
    premature = [
        line
        for line in code.splitlines()
        if "mksafe(" in line and not line.startswith("radio = mksafe(")
    ]
    assert premature == [], f"mksafe applied before the air fallback chooses: {premature}"


def test_the_fallback_has_no_always_ready_child(air_chain):
    """blank() in the list would make everything after it unreachable, as mksafe did.

    The chain needs no blank child: mksafe *is* the blank, applied last.
    """
    assert "blank()" not in air_chain, air_chain


def test_catalog_music_yields_promptly_to_a_queued_song(air_chain):
    """track_sensitive=false, or a queued song waits out the catalog track (RAD-08)."""
    assert "track_sensitive=false" in air_chain, air_chain


def test_the_queue_is_preferred_over_catalog_music(air_chain):
    """Order is the priority: a listener's queue outranks the station's own picks."""
    children = air_chain[air_chain.index("[") + 1 : air_chain.index("]")]
    names = [name.strip() for name in children.split(",")]
    assert names == ["radio_queue", "fallback_music"], names


def test_the_catalog_fallback_plays_only_nameable_catalog_songs(code):
    """/audio_library is scanned recursively and also holds stems, previews and takes.

    A lone Demucs stem is not what the station is for, and its filename carries no
    song id, so the radio page could not name what a listener was hearing (RAD-05).
    """
    assert "check_next=is_catalog_song" in code
    pattern = re.search(r'string\.match\(pattern="([^"]+)"', code)
    assert pattern, "the catalog filter must match on the request's own path"
    catalog_only = re.compile(pattern.group(1))

    assert catalog_only.search("/audio_library/1863_Thats_the_Way_1st_try.mp3")
    for rejected in [
        "/audio_library/produced/2274/stems/29/previews/guitar.opus",
        "/audio_library/produced/1004/stems/14/vocals.wav",
        "/audio_library/sessions/3/takes/7/vocals.flac",
        "/audio_library/produced/1004_x.mp3",
        "/audio_library/misc_track.mp3",
    ]:
        assert not catalog_only.search(rejected), rejected


def test_each_source_still_tags_its_own_tracks(code):
    """How the backend knows whether what is on the air was queued (issue #101).

    The tag is the stream's own answer; queue membership cannot tell the two apart.
    Now that catalog music can actually play, the "fallback" label is reachable.
    """
    assert '[("bigflavor_source", "queue")]' in code
    assert '[("bigflavor_source", "fallback")]' in code
    assert 'source = m["bigflavor_source"],' in code
