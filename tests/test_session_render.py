"""Rendering a detected take links each stem to its own channel.

The band can give two mics one name — a real session has two tracks called
"Drums in stereo". The scan used to link a stem to its channel by that name, so
both drum stems pointed at the same ``session_tracks`` row. ``render_take`` now
carries each track's stored id through by its source file. No ffmpeg: the
WavPack slice is replaced by a tone.
"""
import numpy as np
import soundfile as sf

from src.production import session_render, wavpack_io
from src.production.session_detect import Take, Track

_RATE = 8000


def _track(name: str, source_name: str) -> Track:
    loud = np.full(100, 0.5)
    return Track(
        name=name,
        source_name=source_name,
        position=0.0,
        envelope=wavpack_io.Envelope(rms=loud, peak=loud.copy(), fps=10),
    )


def _fake_slice(source, output_path, start, duration, sample_rate=None, channels=None):
    t = np.arange(int(duration * _RATE)) / _RATE
    sf.write(str(output_path), 0.5 * np.sin(2 * np.pi * 220 * t), _RATE)
    return str(output_path)


def test_two_mics_with_one_name_keep_their_own_track_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(wavpack_io, "extract_segment", _fake_slice)
    tracks = [
        _track("Drums in stereo", "drums-left.wv"),
        _track("Drums in stereo", "drums-right.wv"),
        _track("4 Kev Vox", "kev.wv"),
    ]
    sources = {track.source_name: tmp_path / track.source_name for track in tracks}

    rendered = session_render.render_take(
        Take(start=1.0, end=3.0), tracks, sources, tmp_path / "take",
        sample_rate=_RATE,
        track_ids={"drums-left.wv": 67, "drums-right.wv": 68, "kev.wv": 56},
    )

    assert [(stem.name, stem.display_name, stem.track_id) for stem in rendered.stems] == [
        ("drums", "Drums in stereo", 67),
        ("drums-2", "Drums in stereo", 68),
        ("vocals", "4 Kev Vox", 56),
    ]
