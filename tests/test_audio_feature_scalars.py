"""librosa results are read as scalars without tripping over numpy 2 (issue #107).

`librosa.beat.beat_track` hands back its tempo as a 1-element array. Under numpy
2.5 (the backend image) `float()` on such an array raises "only 0-dimensional
arrays can be converted to Python scalars"; the feature extractor caught that with
a blanket `except`, logged "no usable features", and returned an empty dict. The
effect was silent and total: every song indexed after the librosa/numpy upgrade
got no tempo, key or duration, which is how the 74 songs back-filled for issue
#107 came back empty on the first run while the 1,341 older rows -- indexed before
the upgrade -- still had theirs.

The host running these tests may have an older numpy where the same `float()` only
warns, so pinning the *exception* would pass for the wrong reason. These tests pin
the behaviour that matters instead: whatever shape librosa returns, a plain float
comes out.
"""
import numpy as np
import pytest

from src.rag.audio_embedding_extractor import as_scalar


@pytest.mark.parametrize("value, expected", [
    (np.array([123.45]), 123.45),      # what beat_track actually returns
    (np.array(123.45), 123.45),        # 0-d array
    (np.float64(123.45), 123.45),      # numpy scalar
    (123.45, 123.45),                  # plain float, e.g. get_duration
    (0.0, 0.0),                        # a falsy value is still a value
])
def test_a_librosa_result_reads_as_a_plain_float(value, expected):
    result = as_scalar(value)

    assert result == pytest.approx(expected)
    assert type(result) is float


def test_a_multi_element_array_takes_the_first_value_rather_than_raising():
    # beat_track has returned both shapes across versions; the point is that the
    # extractor keeps working instead of losing the whole feature set.
    assert as_scalar(np.array([120.0, 240.0])) == pytest.approx(120.0)


def test_an_empty_result_is_not_silently_turned_into_a_number():
    # Nothing to report should surface, not become 0 bpm and look like real data.
    with pytest.raises(IndexError):
        as_scalar(np.array([]))
