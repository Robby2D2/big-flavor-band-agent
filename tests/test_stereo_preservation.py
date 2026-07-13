"""
Channel-count preservation tests for the production MCP tools (issue #55).

Synthesizes small mono and stereo WAV fixtures (distinct L/R content) and runs
each write-path production tool, asserting that: the call succeeds, the output
keeps the input's channel count, and stereo outputs keep distinct
(non-duplicated) channels. No live database or LLM is used — the server's
db_manager stays None.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# Make the repo root importable when running `pytest tests/` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip("librosa")
pytest.importorskip("mcp")
sf = pytest.importorskip("soundfile")

from src.production.big_flavor_mcp import BigFlavorMCPServer

SR = 22050
DURATION = 3.0
N_SAMPLES = int(SR * DURATION)


def _tone(freq: float, amplitude: float = 0.4) -> np.ndarray:
    t = np.linspace(0, DURATION, N_SAMPLES, endpoint=False)
    return (amplitude * np.sin(2 * np.pi * freq * t)).astype(np.float32)


@pytest.fixture(scope="module")
def server() -> BigFlavorMCPServer:
    return BigFlavorMCPServer(enable_audio_analysis=True)


@pytest.fixture(scope="module")
def stereo_wav(tmp_path_factory) -> Path:
    """Stereo fixture with deliberately different left/right content."""
    path = tmp_path_factory.mktemp("audio") / "stereo.wav"
    rng = np.random.default_rng(55)
    left = _tone(440) + rng.normal(0, 0.01, N_SAMPLES).astype(np.float32)
    right = _tone(587) + rng.normal(0, 0.01, N_SAMPLES).astype(np.float32)
    sf.write(str(path), np.stack([left, right], axis=1), SR)
    return path


@pytest.fixture(scope="module")
def mono_wav(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("audio") / "mono.wav"
    rng = np.random.default_rng(56)
    mono = _tone(330) + rng.normal(0, 0.01, N_SAMPLES).astype(np.float32)
    sf.write(str(path), mono, SR)
    return path


def _assert_channels(path, expected: int) -> None:
    info = sf.info(str(path))
    assert info.channels == expected, (
        f"{path} has {info.channels} channel(s), expected {expected}"
    )


def _assert_distinct_stereo(path) -> None:
    data, _ = sf.read(str(path))
    assert data.ndim == 2 and data.shape[1] == 2
    assert not np.allclose(data[:, 0], data[:, 1]), (
        "stereo output collapsed to duplicated mono"
    )


TOOLS = [
    ("trim_silence", lambda srv, inp, out: srv.trim_silence(str(inp), -40, str(out))),
    ("reduce_noise", lambda srv, inp, out: srv.reduce_noise(str(inp), 0.5, 0.7, str(out))),
    ("apply_eq", lambda srv, inp, out: srv.apply_eq(str(inp), 30, None, 1000, 3, str(out))),
    ("normalize_audio", lambda srv, inp, out: srv.normalize_audio(str(inp), -3, True, str(out))),
    ("apply_mastering", lambda srv, inp, out: srv.apply_mastering(str(inp), -14.0, str(out))),
    ("remove_artifacts", lambda srv, inp, out: srv.remove_artifacts(str(inp), 0.5, str(out))),
    ("correct_pitch", lambda srv, inp, out: srv.correct_pitch(str(inp), 2, False, str(out))),
]
TOOL_IDS = [name for name, _ in TOOLS]


@pytest.mark.parametrize("name,run", TOOLS, ids=TOOL_IDS)
async def test_stereo_preserved(name, run, server, stereo_wav, tmp_path):
    out = tmp_path / f"{name}_stereo.wav"
    result = await run(server, stereo_wav, out)
    assert result.get("status") == "success", result
    _assert_channels(out, 2)
    _assert_distinct_stereo(out)


@pytest.mark.parametrize("name,run", TOOLS, ids=TOOL_IDS)
async def test_mono_preserved(name, run, server, mono_wav, tmp_path):
    out = tmp_path / f"{name}_mono.wav"
    result = await run(server, mono_wav, out)
    assert result.get("status") == "success", result
    _assert_channels(out, 1)


async def test_auto_clean_chain_keeps_stereo(server, stereo_wav, tmp_path):
    out = tmp_path / "auto_clean_stereo.wav"
    result = await server.auto_clean_recording(str(stereo_wav), str(out), "moderate", False)
    assert result.get("status") == "success", result
    _assert_channels(out, 2)
    _assert_distinct_stereo(out)


async def test_auto_clean_chain_keeps_mono(server, mono_wav, tmp_path):
    out = tmp_path / "auto_clean_mono.wav"
    result = await server.auto_clean_recording(str(mono_wav), str(out), "moderate", False)
    assert result.get("status") == "success", result
    _assert_channels(out, 1)
