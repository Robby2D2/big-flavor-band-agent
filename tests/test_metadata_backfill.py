"""Assert-based tests for the catalog metadata back-fill (issue #52).

Cover the pure helpers and the LLM-routed genre classifier without a live DB,
real audio, or a real model:

- backfill_audio_metadata.derive_audio_metadata — librosa feature -> song columns.
- derive_genre.parse_genre / build_user_prompt — JSON parsing + prompt shaping.
- derive_genre.classify — uses an injected fake LLMProvider, including the
  corrective retry path, so the LLM seam is exercised without Anthropic/Ollama.
"""

import sys
from pathlib import Path

import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag import backfill_audio_metadata as bam
from src.rag import derive_genre


# ---- derive_audio_metadata (pure) ----

def test_derive_audio_metadata_rounds_duration_and_keeps_tempo():
    features = {"librosa_features": {"duration": 212.7, "tempo": 118.4}}
    derived = bam.derive_audio_metadata(features)
    assert derived == {"duration_seconds": 213, "tempo_bpm": 118.4}
    # duration_seconds is an INTEGER column.
    assert isinstance(derived["duration_seconds"], int)


def test_derive_audio_metadata_handles_partial_features():
    only_duration = bam.derive_audio_metadata({"librosa_features": {"duration": 90.0}})
    assert only_duration == {"duration_seconds": 90, "tempo_bpm": None}


def test_derive_audio_metadata_returns_none_on_empty_features():
    # extract_all_features returns {} (no librosa_features) when analysis fails.
    assert bam.derive_audio_metadata({}) is None
    assert bam.derive_audio_metadata({"librosa_features": {}}) is None


def test_resolve_audio_path_globs_by_song_id(tmp_path, monkeypatch):
    monkeypatch.setattr(bam, "AUDIO_LIBRARY_DIR", tmp_path)
    (tmp_path / "5_some_song.mp3").write_bytes(b"ID3")
    (tmp_path / "50_other.mp3").write_bytes(b"ID3")  # must not match song 5

    resolved = bam.resolve_audio_path(5)
    assert resolved == tmp_path / "5_some_song.mp3"
    assert bam.resolve_audio_path(999) is None


# ---- parse_genre (pure) ----

def test_parse_genre_accepts_valid_label_in_json():
    assert derive_genre.parse_genre('{"genre": "funk"}') == "funk"
    # Surrounding prose is tolerated as long as a JSON object is present.
    assert derive_genre.parse_genre('Sure! {"genre": "Folk"} hope that helps') == "folk"


def test_parse_genre_rejects_out_of_vocabulary_and_garbage():
    assert derive_genre.parse_genre('{"genre": "polka"}') is None
    assert derive_genre.parse_genre("no json here") is None
    assert derive_genre.parse_genre('{"genre": }') is None


def test_build_user_prompt_includes_lyrics_and_caps_length():
    long_lyrics = "la " * 2000
    song = {"title": "Test", "tempo_bpm": 120.0, "lyrics": long_lyrics}
    prompt = derive_genre.build_user_prompt(song)
    assert "Title: Test" in prompt
    assert "Tempo (BPM): 120" in prompt
    assert "[…]" in prompt  # truncated
    assert len(prompt) < len(long_lyrics)


# ---- classify (LLM seam, fake provider) ----

class FakeLLM:
    """LLMProvider stand-in returning queued canned replies, no network."""

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = 0

    async def generate_response(self, messages, system=None, max_tokens=4096, temperature=1.0):
        self.calls += 1
        return self._replies.pop(0)


@pytest.mark.asyncio
async def test_classify_returns_genre_on_first_valid_reply():
    llm = FakeLLM(['{"genre": "blues"}'])
    song = {"title": "Midnight", "lyrics": "woke up this morning"}
    genre = await derive_genre.classify(llm, song, temperature=0.2)
    assert genre == "blues"
    assert llm.calls == 1  # no retry needed


@pytest.mark.asyncio
async def test_classify_retries_once_on_invalid_then_succeeds():
    llm = FakeLLM(['{"genre": "polka"}', '{"genre": "folk"}'])
    song = {"title": "Old Road", "lyrics": "down the dusty trail"}
    genre = await derive_genre.classify(llm, song, temperature=0.2)
    assert genre == "folk"
    assert llm.calls == 2  # one corrective retry


@pytest.mark.asyncio
async def test_classify_gives_up_after_failed_retry():
    llm = FakeLLM(['nonsense', 'still nonsense'])
    song = {"title": "Unknowable", "lyrics": "??"}
    genre = await derive_genre.classify(llm, song, temperature=0.2)
    assert genre is None
    assert llm.calls == 2
