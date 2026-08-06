"""Tests for compressed playback copies (src/production/audio_preview.py).

ffmpeg is never actually invoked here — like Demucs elsewhere in the suite, it
is monkeypatched out, so these cover the logic around the encode: where a
preview lands, when the encode is skipped entirely, that a built preview is
reused, and that a partial file is never left behind to masquerade as a cache
hit.
"""
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.production import audio_preview


def _write_wav(path: Path, seconds: float = 0.25, sr: int = 8000):
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    mono = 0.3 * np.sin(2 * np.pi * 220.0 * t)
    sf.write(str(path), np.column_stack([mono, mono]).astype(np.float32), sr)


def _fake_ffmpeg(monkeypatch, *, writes=True, error=None, calls=None):
    """Stand in for the ffmpeg subprocess, writing the .part file it promises."""

    def run(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        if error is not None:
            raise error
        if writes:
            Path(cmd[-1]).write_bytes(b"fake-opus-bytes")
        return subprocess.CompletedProcess(cmd, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", run)


# ---- where previews land ----

def test_stem_preview_sits_in_a_previews_dir_beside_the_stem(tmp_path):
    """Inheriting the stem-set directory is what ties a preview to its set."""
    stem = tmp_path / "produced" / "1140" / "stems" / "9" / "vocals.wav"
    preview = audio_preview.stem_preview_path(stem)

    assert preview.parent == stem.parent / audio_preview.PREVIEW_SUBDIR
    assert preview.name == "vocals" + audio_preview.PREVIEW_SUFFIX


def test_version_preview_lands_under_produced(tmp_path):
    """A version's source can be on the read-only catalog mount, so it can't go beside it."""
    produced = tmp_path / "produced"
    source = tmp_path / "1140_Hey_Hey_My_My.mp3"

    preview = audio_preview.version_preview_path(source, produced)

    assert preview.parent == produced / audio_preview.PREVIEW_SUBDIR
    assert preview.name == "1140_Hey_Hey_My_My" + audio_preview.PREVIEW_SUFFIX
    assert produced in preview.parents


def test_version_previews_of_different_sources_do_not_collide(tmp_path):
    produced = tmp_path / "produced"
    original = audio_preview.version_preview_path(tmp_path / "1650_song.mp3", produced)
    cleaned = audio_preview.version_preview_path(
        tmp_path / "1650_cleaned_1785559473.wav", produced
    )
    assert original != cleaned


# ---- building ----

def test_already_compressed_source_is_passed_through(tmp_path, monkeypatch):
    """An MP3 is served as-is: re-encoding costs a generation of quality to save little."""
    calls = []
    _fake_ffmpeg(monkeypatch, calls=calls)
    source = tmp_path / "song.mp3"
    source.write_bytes(b"mp3-bytes")
    out = tmp_path / "previews" / "song.opus"

    served = audio_preview.build_preview(str(source), str(out))

    assert served == str(source)
    assert not out.exists()
    assert calls == [], "ffmpeg should not run for an already-compressed source"


def test_wav_is_transcoded_once_then_reused(tmp_path, monkeypatch):
    calls = []
    _fake_ffmpeg(monkeypatch, calls=calls)
    source = tmp_path / "vocals.wav"
    _write_wav(source)
    out = audio_preview.stem_preview_path(source)

    first = audio_preview.build_preview(str(source), str(out))
    second = audio_preview.build_preview(str(source), str(out))

    assert first == second == str(out)
    assert out.exists()
    assert len(calls) == 1, "an existing preview must not be re-encoded"


def test_encode_uses_the_configured_codec_and_leaves_no_part_file(tmp_path, monkeypatch):
    calls = []
    _fake_ffmpeg(monkeypatch, calls=calls)
    source = tmp_path / "vocals.wav"
    _write_wav(source)
    out = audio_preview.stem_preview_path(source)

    audio_preview.build_preview(str(source), str(out))

    cmd = calls[0]
    assert audio_preview.PREVIEW_CODEC in cmd
    assert audio_preview.PREVIEW_BITRATE in cmd
    assert "-nostdin" in cmd, "ffmpeg must not consume the server's stdin"
    assert cmd[-1].endswith(".part"), "encode should go to a temp name"
    assert list(out.parent.glob("*.part")) == []
    # The temp name has no recognisable extension, so the container format has
    # to be stated outright — without this ffmpeg cannot choose a muxer and the
    # encode fails before writing a byte.
    assert cmd[cmd.index("-f") + 1] == audio_preview.PREVIEW_FORMAT


def test_failed_encode_raises_and_cleans_up(tmp_path, monkeypatch):
    """A failed encode must not leave a partial file that later reads as a cache hit."""
    _fake_ffmpeg(
        monkeypatch,
        error=subprocess.CalledProcessError(1, "ffmpeg", b"", b"Invalid data"),
    )
    source = tmp_path / "vocals.wav"
    _write_wav(source)
    out = audio_preview.stem_preview_path(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_name(out.name + ".part").write_bytes(b"half-written")

    with pytest.raises(subprocess.CalledProcessError):
        audio_preview.build_preview(str(source), str(out))

    assert not out.exists()
    assert list(out.parent.glob("*.part")) == []


def test_missing_ffmpeg_propagates_file_not_found(tmp_path, monkeypatch):
    """Running outside Docker has no ffmpeg; the router turns this into a 503."""
    _fake_ffmpeg(monkeypatch, error=FileNotFoundError("ffmpeg"))
    source = tmp_path / "vocals.wav"
    _write_wav(source)

    with pytest.raises(FileNotFoundError):
        audio_preview.build_preview(
            str(source), str(audio_preview.stem_preview_path(source))
        )
