"""The CLAP audio path produces a vector, and a missing one is a failure (issue #111).

Audio-similarity search is built on CLAP, and CLAP never ran: the processor was
called as `clap_processor(audios=...)`, transformers had renamed that kwarg to
`audio` and raises on the old one, `extract_clap_embedding` caught the exception
and returned None, and `index_audio_file` stored the row and returned True anyway.
So every one of the 1,415 rows in `audio_embeddings` held a NULL `clap_embedding`
and a librosa-only `combined_embedding` for ten months, while the batch indexer
reported `{'total': 74, 'success': 74, 'failed_files': []}`.

Two things are pinned here, because two things were wrong:

1. **The call.** The fake processor below raises on `audios=` exactly as
   transformers does, so the old code cannot pass these tests. And the embedding
   is read out of `pooler_output`, which is what transformers 5's
   `get_audio_features` returns -- the kwarg fix alone still blew up on
   `'BaseModelOutputWithPooling' object has no attribute 'cpu'`.

2. **The report.** A row whose CLAP half could not be produced is now a failure
   rather than a silent success (CAT-12), which is the part that would have
   surfaced this in 2025.

CLAP itself is never loaded here -- per TESTING.md the model is too heavy for a
test, so the orchestration around it is tested with fakes.
"""
import numpy as np
import pytest

from src.rag.audio_embedding_extractor import (
    AudioEmbeddingExtractor,
    as_embedding,
)


# --- the shape transformers hands back -------------------------------------


class _PoolerOutput:
    """Stands in for transformers 5's BaseModelOutputWithPooling."""

    def __init__(self, pooler_output):
        self.pooler_output = pooler_output
        self.last_hidden_state = "not the embedding"


def test_the_embedding_is_read_out_of_pooler_output():
    # transformers 5: get_audio_features returns a model output object whose
    # pooler_output is the 512-dim projected embedding.
    vector = np.arange(512, dtype=np.float32)

    assert as_embedding(_PoolerOutput(vector)) is vector


def test_a_bare_tensor_is_still_read_as_the_embedding():
    # transformers 4 (what the host venv has): the tensor comes back directly.
    vector = np.arange(512, dtype=np.float32)

    assert as_embedding(vector) is vector


# --- extract_clap_embedding ------------------------------------------------


class _FakeTensor:
    """The slice of tensor behaviour extract_clap_embedding uses."""

    def __init__(self, array):
        self._array = np.asarray(array)

    def to(self, _device):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._array


class _FakeProcessor:
    """A processor that accepts `audio=` and rejects `audios=` like transformers.

    transformers raises ValueError("You passed keyword argument `audios` which is
    deprecated. Please use `audio` instead."), so a test using this fake fails
    against the pre-fix extractor rather than passing for the wrong reason.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, audio=None, audios=None, sampling_rate=None, return_tensors=None):
        if audios is not None:
            raise ValueError(
                "You passed keyword argument `audios` which is deprecated. "
                "Please use `audio` instead."
            )
        if audio is None:
            raise ValueError("no audio was passed")
        self.calls.append({"sampling_rate": sampling_rate, "return_tensors": return_tensors})
        return {"input_features": _FakeTensor([[0.0]]), "is_longer": _FakeTensor([[False]])}


class _FakeClapModel:
    def __init__(self, vector):
        self._vector = vector
        self.seen_keys = None

    def get_audio_features(self, **inputs):
        self.seen_keys = sorted(inputs)
        # One row, because the extractor takes [0].
        return _PoolerOutput(_FakeTensor(np.asarray([self._vector])))


def _extractor_with_fakes(vector, monkeypatch):
    """An extractor wired to fakes, without loading CLAP or touching a GPU."""
    extractor = AudioEmbeddingExtractor(use_clap=False)
    extractor.use_clap = True
    extractor.device = "cpu"
    extractor.clap_processor = _FakeProcessor()
    extractor.clap_model = _FakeClapModel(vector)
    monkeypatch.setattr(
        "src.rag.audio_embedding_extractor.librosa.load",
        lambda path, sr=None, duration=None: (np.zeros(int(sr or 48000), dtype=np.float32), sr),
    )
    return extractor


def test_the_clap_path_returns_a_vector_rather_than_none(monkeypatch):
    # The regression in one line: this returned None for every song in the catalog.
    raw = np.linspace(1.0, 2.0, 512, dtype=np.float32)
    extractor = _extractor_with_fakes(raw, monkeypatch)

    embedding = extractor.extract_clap_embedding("any.mp3")

    assert embedding is not None, "the CLAP path silently produced no embedding"
    assert embedding.shape == (512,)
    assert np.linalg.norm(embedding) == pytest.approx(1.0), "embedding should be unit-norm"


def test_the_processor_is_called_with_audio_not_audios(monkeypatch):
    extractor = _extractor_with_fakes(np.ones(512, dtype=np.float32), monkeypatch)

    extractor.extract_clap_embedding("any.mp3", sr=48000)

    assert extractor.clap_processor.calls == [
        {"sampling_rate": 48000, "return_tensors": "pt"}
    ]
    # Whatever the processor produced is what the model is asked about.
    assert extractor.clap_model.seen_keys == ["input_features", "is_longer"]


def test_an_unreadable_file_is_none_rather_than_an_exception(monkeypatch):
    extractor = _extractor_with_fakes(np.ones(512, dtype=np.float32), monkeypatch)

    def boom(*_args, **_kwargs):
        raise RuntimeError("cannot decode")

    monkeypatch.setattr("src.rag.audio_embedding_extractor.librosa.load", boom)

    # None is the right answer here -- a search must degrade, not raise. What must
    # not happen is a None being *stored*, which is what index_audio_file now
    # refuses (see below).
    assert extractor.extract_clap_embedding("broken.mp3") is None


# --- the combined representation ------------------------------------------


def test_a_clap_combined_embedding_is_549_dimensions():
    # 37 librosa dimensions + CLAP's 512. This is the width migration 19 restores
    # the column to; a 512-wide column silently made every insert fail instead.
    extractor = AudioEmbeddingExtractor(use_clap=False)

    combined = extractor.create_combined_embedding(
        {"tempo": 120.0, "mfcc_mean": [0.5] * 13, "chroma_mean": [0.2] * 12,
         "tonnetz_mean": [0.1] * 6},
        clap_embedding=np.linspace(0.0, 1.0, 512, dtype=np.float32),
    )

    assert combined.shape == (549,)
    assert np.linalg.norm(combined) == pytest.approx(1.0)


def test_the_librosa_fallback_stays_512_and_so_cannot_share_the_column():
    # Deliberately a different width from the CLAP representation: a fallback
    # vector physically cannot be stored beside CLAP ones, so the catalog cannot
    # end up comparing two embedding spaces (CAT-11).
    extractor = AudioEmbeddingExtractor(use_clap=False)

    combined = extractor.create_combined_embedding({"tempo": 120.0}, clap_embedding=None)

    assert combined.shape == (512,)


# --- a partial audio index is a failure (CAT-12) ---------------------------


class _RecordingConn:
    def __init__(self):
        self.queries = []

    async def fetchval(self, query, *args):
        self.queries.append((query, args))
        return 4242

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _RecordingPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return self._conn


class _StubDb:
    def __init__(self, conn):
        self.pool = _RecordingPool(conn)


def _rag_with_features(features, conn):
    """A SongRAGSystem with no models loaded, whose extractor returns `features`."""
    from src.rag.big_flavor_rag import SongRAGSystem

    rag = SongRAGSystem.__new__(SongRAGSystem)
    rag.db = _StubDb(conn)

    class _Extractor:
        def extract_all_features(self, _path):
            return features

    rag.embedding_extractor = _Extractor()
    return rag


@pytest.mark.asyncio
async def test_a_song_with_no_clap_embedding_is_not_indexed():
    # The bug's reporting half: this returned True and wrote a librosa-only row,
    # so index_audio_batch counted 74/74 successes with zero CLAP embeddings.
    conn = _RecordingConn()
    rag = _rag_with_features(
        {
            "librosa_features": {"tempo": 120.0},
            "clap_embedding": None,
            "combined_embedding": [0.0] * 512,
        },
        conn,
    )

    indexed = await rag.index_audio_file("/app/audio_library/1_Song.mp3", 1)

    assert indexed is False, "a partial audio index must be reported as a failure"
    assert conn.queries == [], "nothing should be written for a partial audio index"


@pytest.mark.asyncio
async def test_a_song_with_a_clap_embedding_is_indexed():
    conn = _RecordingConn()
    rag = _rag_with_features(
        {
            "librosa_features": {"tempo": 120.0},
            "clap_embedding": [0.1] * 512,
            "combined_embedding": [0.01] * 549,
        },
        conn,
    )

    indexed = await rag.index_audio_file("/app/audio_library/1_Song.mp3", 1)

    assert indexed is True
    assert len(conn.queries) == 1
    query, args = conn.queries[0]
    assert "INSERT INTO audio_embeddings" in query
    assert args[0] == 1
    assert args[1] == "/app/audio_library/1_Song.mp3"
    assert args[3] is not None, "the CLAP embedding must reach the database"


@pytest.mark.asyncio
async def test_a_batch_reports_the_partial_song_as_failed():
    # The summary the spec asks about: a run's success count must never exceed the
    # number of songs with a complete audio index.
    conn = _RecordingConn()
    rag = _rag_with_features(
        {
            "librosa_features": {"tempo": 120.0},
            "clap_embedding": None,
            "combined_embedding": [0.0] * 512,
        },
        conn,
    )

    stats = await rag.index_audio_batch([("/app/audio_library/1_Song.mp3", 1)])

    assert stats["total"] == 1
    assert stats["success"] == 0
    assert stats["failed"] == 1
    assert stats["failed_files"] == [("/app/audio_library/1_Song.mp3", 1)]
