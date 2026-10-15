"""The radio page shows how many people are actually listening (RAD-14).

The count comes from Icecast — clients connected to the stream — not from the
radio page's own polling, which counts open tabs whether or not anyone pressed
play. A count that cannot be read is None, never a 0 that may be wrong.

No real Icecast: the status payloads and the HTTP client are faked.
"""
import pytest

from src.api import radio_service
from src.api.radio_service import fetch_stream_listeners, listeners_from_icestats


def _source(mount="/stream", listeners=3):
    return {"listenurl": f"http://bigflavor.useunix.com:8000{mount}", "listeners": listeners}


def test_counts_listeners_on_the_single_mount():
    assert listeners_from_icestats({"icestats": {"source": _source(listeners=4)}}) == 4


def test_picks_the_stream_mount_when_there_are_several():
    payload = {"icestats": {"source": [_source("/other", 9), _source("/stream", 2)]}}
    assert listeners_from_icestats(payload) == 2


def test_no_source_connected_means_nobody_is_listening():
    assert listeners_from_icestats({"icestats": {"host": "x"}}) == 0


def test_unreadable_payload_is_unknown_not_zero():
    assert listeners_from_icestats({"not": "icecast"}) is None
    assert listeners_from_icestats(None) is None
    assert listeners_from_icestats({"icestats": {"source": _source(listeners="lots")}}) is None


@pytest.mark.asyncio
async def test_unreachable_icecast_is_unknown(monkeypatch):
    class Boom:
        async def __aenter__(self):
            raise ConnectionError("icecast down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(radio_service.httpx, "AsyncClient", lambda **kwargs: Boom())
    assert await fetch_stream_listeners() is None
