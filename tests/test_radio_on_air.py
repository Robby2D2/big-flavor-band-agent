"""The radio state is reconciled against the audio actually on the air (issue #101).

The old backend clock decided what was playing by adding wall-clock time to a
position and comparing it against a catalog duration, so it drifted away from the
stream and a song with no duration pinned the display forever. These tests cover
the replacement: the stream is asked what it is playing, and the state follows the
answer.

They are the *properties* that kept breaking, not the numbers:
- position comes from the stream every time, so it cannot accumulate error;
- nothing compares a position against a duration, so a missing duration cannot pin
  anything (CAT-02);
- audible audio outside the queue is named as fallback rather than reported as
  nothing playing (the visible form of RAD-02) — including a file the catalog has
  no row for, which the stream can and does pick (issue #104);
- a stream that cannot be asked is reported as unknown, never as a guess (PLAT-07).

No live Postgres, no real LLM, no real stream: the catalog lookup and the harbor
call are faked.
"""
import time

import pytest

from src.api import radio_service
from src.api.radio_service import (
    mark_stream_unknown,
    reconcile_with_stream,
    resolve_on_air_song,
    song_id_from_filename,
)


def _state(**overrides):
    state = {
        "current_song": None,
        "queue": [],
        "is_playing": False,
        "position": 0,
        "last_update": 0.0,
        "stream_known": False,
        "current_song_source": None,
        "stream_duration": None,
    }
    state.update(overrides)
    return state


def _song(song_id, duration=180):
    return {"id": song_id, "title": f"Song {song_id}", "duration": duration}


def _on_air(filename, elapsed=10.0, remaining=170.0, source="queue"):
    return {
        "filename": filename,
        "title": "whatever ID3 says",
        "source": source,
        "elapsed": elapsed,
        "remaining": remaining,
    }


# --- Identity: the file on air, not the ID3 title -------------------------

def test_song_id_comes_from_the_catalog_filename():
    assert song_id_from_filename("/audio_library/1653_So_Tired_you_heard_it_baby.mp3") == 1653


@pytest.mark.parametrize("filename", [None, "", "no_leading_id.mp3", "/audio_library/"])
def test_unrecognisable_filenames_have_no_song_id(filename):
    assert song_id_from_filename(filename) is None


def test_published_version_file_is_resolved_through_the_overrides():
    """A published version (issue #30) is served from its own path, which need not
    carry the song id, so the override table is the reverse lookup."""
    radio_service.set_published_version_paths(
        {42: "/app/audio_library/produced/42/cleaned_v3.mp3"}
    )
    try:
        assert song_id_from_filename("/audio_library/produced/42/cleaned_v3.mp3") == 42
        assert song_id_from_filename("/audio_library/produced/42/other.mp3") is None
    finally:
        radio_service.set_published_version_paths({})


# --- Resolving what is on the air ----------------------------------------

@pytest.mark.asyncio
async def test_on_air_song_found_in_the_queue_is_labelled_queue():
    queue = [_song(1), _song(2)]

    song, source = await resolve_on_air_song(_on_air("/audio_library/2_two.mp3"), queue)

    assert song is queue[1]
    assert source == "queue"
    assert len(queue) == 2, "resolving must not mutate the queue"


@pytest.mark.asyncio
async def test_a_song_the_stream_picked_itself_is_looked_up_in_the_catalog(monkeypatch):
    """Audible audio must never be reported as nothing playing, so a song nobody
    queued is named from the catalog (the visible form of RAD-02)."""
    class FakeDb:
        async def get_song(self, song_id):
            return {"id": song_id, "title": "Library Pick", "duration_seconds": 240}

    async def fake_get_db():
        return FakeDb()

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)

    song, source = await resolve_on_air_song(
        _on_air("/audio_library/900_pick.mp3", source="fallback"), []
    )

    assert source == "fallback"
    assert song == {"id": 900, "title": "Library Pick", "duration": 240}


@pytest.mark.asyncio
async def test_the_source_label_is_the_streams_answer_not_queue_membership(monkeypatch):
    """The playlist holds the current song as well as the queue and can replay it, so
    "is it still in our queue?" cannot tell a queued song from fallback music. Each
    Liquidsoap source tags its own tracks, and that tag is what is reported — here,
    a song no longer in the queue that the queue playlist is still playing."""
    class FakeDb:
        async def get_song(self, song_id):
            return {"id": song_id, "title": "Replayed", "duration_seconds": 100}

    async def fake_get_db():
        return FakeDb()

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)

    _song_row, source = await resolve_on_air_song(
        _on_air("/audio_library/1_one.mp3", source="queue"), []
    )

    assert source == "queue"


@pytest.mark.asyncio
async def test_unknown_file_on_air_resolves_to_nothing():
    song, source = await resolve_on_air_song(_on_air("/audio_library/sessions/take.flac"), [])

    assert song is None and source is None


@pytest.mark.asyncio
async def test_the_song_already_current_is_not_re_read_from_the_catalog(monkeypatch):
    """Reconciliation runs every second and a song is on the air for minutes, so the
    steady state must not be a catalog query a second."""
    async def fake_get_db():
        raise AssertionError("the catalog must not be re-read for the current song")

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)
    current = {"id": 900, "title": "Library Pick", "duration": 240}

    song, source = await resolve_on_air_song(
        _on_air("/audio_library/900_pick.mp3", source="fallback"), [], current
    )

    assert song is current
    assert source == "fallback"


# --- Reconciling the state against the stream ----------------------------

def test_the_on_air_song_leaves_the_queue_and_becomes_current():
    state = _state(queue=[_song(1), _song(2)])

    queue_changed = reconcile_with_stream(state, _on_air("/audio_library/1_one.mp3"),
                                          state["queue"][0], "queue")

    assert queue_changed is True
    assert state["current_song"]["id"] == 1
    assert state["current_song_source"] == "queue"
    assert [s["id"] for s in state["queue"]] == [2], "a song the stream started is not up next"
    assert state["stream_known"] is True


def test_fallback_music_is_named_without_touching_the_queue():
    state = _state(queue=[_song(1)])
    library_pick = {"id": 900, "title": "Library Pick", "duration": 240}

    queue_changed = reconcile_with_stream(
        state, _on_air("/audio_library/900_pick.mp3", source="fallback"),
        library_pick, "fallback"
    )

    assert queue_changed is False
    assert state["current_song"]["id"] == 900
    assert state["current_song_source"] == "fallback"
    assert [s["id"] for s in state["queue"]] == [1], "fallback must not consume the queue"


def test_position_is_the_streams_elapsed_time_and_never_accumulates():
    """The drift in issue #101 came from adding elapsed wall time to a running
    total. Position is now overwritten with what the stream reports, so repeated
    reconciliation of the same instant cannot move it."""
    state = _state(current_song=_song(1), position=999)

    for _ in range(5):
        reconcile_with_stream(state, _on_air("/audio_library/1_one.mp3", elapsed=42.5,
                                             remaining=100.0), _song(1), "queue")

    assert state["position"] == 42.5


def test_a_song_with_no_duration_no_longer_pins_now_playing():
    """The old clock only advanced when `duration and duration > 0`, so a catalog row
    with no duration held the display forever. Nothing here reads a duration, and the
    stream supplies one for the progress bar (CAT-02)."""
    state = _state(current_song={"id": 1, "title": "No duration", "duration": None},
                   queue=[{"id": 2, "title": "Next", "duration": None}])

    reconcile_with_stream(state, _on_air("/audio_library/2_next.mp3", elapsed=5.0,
                                         remaining=175.0), state["queue"][0], "queue")

    assert state["current_song"]["id"] == 2, "the display moved when the stream did"
    assert state["stream_duration"] == 180.0


def test_no_stream_duration_when_the_stream_does_not_know_the_length():
    state = _state()

    reconcile_with_stream(state, _on_air("/audio_library/1_one.mp3", elapsed=3.0,
                                         remaining=-1.0), _song(1), "queue")

    assert state["stream_duration"] is None
    assert state["position"] == 3.0


def test_audio_we_cannot_name_reports_no_current_song():
    state = _state(current_song=_song(1), current_song_source="queue")

    reconcile_with_stream(state, _on_air("/audio_library/sessions/take.flac"), None, None)

    assert state["current_song"] is None
    assert state["current_song_source"] is None
    assert state["stream_known"] is True


def test_audio_on_the_air_with_nothing_playing_starts_the_broadcast():
    """Continuous broadcast (issue #79): a state that thought nothing was playing must
    read LIVE once the stream names a song."""
    state = _state(current_song=None, is_playing=False, queue=[_song(1)])

    reconcile_with_stream(state, _on_air("/audio_library/1_one.mp3"), state["queue"][0], "queue")

    assert state["is_playing"] is True


def test_an_explicit_pause_is_not_resumed_by_reconciliation():
    """A pause keeps current_song set with is_playing False; following the stream must
    keep the displayed song honest without undoing the pause (RAD-07)."""
    state = _state(current_song=_song(1), is_playing=False, queue=[_song(2)])

    reconcile_with_stream(state, _on_air("/audio_library/2_two.mp3"), state["queue"][0], "queue")

    assert state["is_playing"] is False
    assert state["current_song"]["id"] == 2


# --- An unreachable stream ------------------------------------------------

def test_unreachable_stream_is_reported_as_unknown_not_as_a_guess():
    state = _state(current_song=_song(1), current_song_source="queue", stream_known=True,
                   position=30)

    mark_stream_unknown(state)

    assert state["stream_known"] is False
    # The stored song stays -- it is what the playlist is built from -- but the API
    # reports stream_known False and the page says unknown rather than naming it.
    assert state["current_song"]["id"] == 1


def test_unknown_transition_is_logged_once_not_once_per_tick(caplog):
    """PLAT-10 wants the reason in the logs; a line a second would bury it."""
    state = _state(stream_known=True)

    with caplog.at_level("WARNING", logger="backend-api"):
        for _ in range(4):
            mark_stream_unknown(state)

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_fetch_on_air_returns_none_when_the_stream_cannot_be_reached(monkeypatch):
    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            raise OSError("connection refused")

    monkeypatch.setattr(radio_service.httpx, "AsyncClient", lambda **kwargs: Boom())

    assert await radio_service.fetch_on_air() is None


@pytest.mark.asyncio
async def test_skip_on_air_reports_failure_rather_than_appearing_to_succeed(monkeypatch):
    """RAD-09: a skip that could not reach the stream must not look like it worked."""
    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url):
            raise OSError("connection refused")

    monkeypatch.setattr(radio_service.httpx, "AsyncClient", lambda **kwargs: Boom())

    assert await radio_service.skip_on_air() is False


def test_reconciliation_keeps_the_state_json_serializable():
    """Radio state round-trips through JSONB, so a reconciled state must contain
    nothing the store cannot serialize."""
    import json

    state = _state(queue=[_song(1)])
    reconcile_with_stream(state, _on_air("/audio_library/1_one.mp3"), state["queue"][0], "queue")
    state["last_update"] = time.time()

    json.dumps(state)


# --- Playable audio the catalog has no row for (issue #104) ---------------
# Making the catalog fallback reachable put files on the air that the catalog does
# not describe: 74 of the 1,415 playable "{song_id}_*.mp3" files have no songs row,
# so ~1 fallback track in 19 used to report nothing playing over audible music.

@pytest.mark.asyncio
async def test_a_fallback_file_with_no_catalog_row_is_named_from_the_stream(monkeypatch):
    """RAD-05: the page must name what is on the air, and the stream knows the
    track's ID3 title even when the catalog has never heard of the file."""
    class FakeDb:
        async def get_song(self, song_id):
            return None

    async def fake_get_db():
        return FakeDb()

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)
    on_air = _on_air("/audio_library/890_KWE_Lull_Me_Away_take_1.mp3", source="fallback")
    on_air["title"] = "KWE -- Lull Me Away -- take 1"

    song, source = await resolve_on_air_song(on_air, [])

    assert source == "fallback"
    assert song == {"id": 890, "title": "KWE -- Lull Me Away -- take 1", "duration": None}


@pytest.mark.asyncio
async def test_an_untagged_file_falls_back_to_its_filename_not_to_silence(monkeypatch):
    class FakeDb:
        async def get_song(self, song_id):
            return None

    async def fake_get_db():
        return FakeDb()

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)
    on_air = _on_air("/audio_library/890_KWE_Lull_Me_Away_take_1.mp3", source="fallback")
    on_air["title"] = ""

    song, _source = await resolve_on_air_song(on_air, [])

    assert song == {"id": 890, "title": "KWE Lull Me Away take 1", "duration": None}


@pytest.mark.asyncio
async def test_a_catalog_lookup_that_fails_still_names_what_is_playing(monkeypatch):
    """A database blip must not make the radio page claim the stream is silent."""
    async def fake_get_db():
        raise OSError("connection refused")

    monkeypatch.setattr(radio_service, "get_db", fake_get_db)
    on_air = _on_air("/audio_library/890_Lull_Me_Away.mp3", source="fallback")
    on_air["title"] = "Lull Me Away"

    song, source = await resolve_on_air_song(on_air, [])

    assert song == {"id": 890, "title": "Lull Me Away", "duration": None}
    assert source == "fallback"


def test_a_stream_named_song_shows_progress_from_the_streams_own_length():
    """It has no catalog duration, so the progress bar depends on the length the
    stream reports -- the same path a catalog song with no duration takes (CAT-02)."""
    state = _state()
    stream_named = {"id": 890, "title": "Lull Me Away", "duration": None}

    reconcile_with_stream(
        state,
        _on_air("/audio_library/890_Lull_Me_Away.mp3", elapsed=18.0, remaining=145.0,
                source="fallback"),
        stream_named, "fallback",
    )

    assert state["current_song"] == stream_named
    assert state["current_song_source"] == "fallback", "the page must still say it is fallback music"
    assert state["stream_duration"] == 163.0


def test_naming_from_the_stream_needs_no_catalog_lookup_and_no_id_guess():
    """Only files whose name carries an id are named this way: an id is what the
    queue, the playlist writer and /api/audio/stream all key on, so inventing one
    would be worse than saying nothing."""
    assert radio_service._song_from_stream(890, {"title": " Lull Me Away ", "filename": "x"}) == {
        "id": 890, "title": "Lull Me Away", "duration": None
    }
    assert radio_service._song_from_stream(890, {}) == {
        "id": 890, "title": "Song 890", "duration": None
    }
    # A published version's file need not start with the id (issue #30), so the
    # prefix is stripped only when it is really there.
    assert radio_service._song_from_stream(
        42, {"filename": "/audio_library/produced/42/cleaned_v3.mp3"}
    )["title"] == "cleaned v3"
