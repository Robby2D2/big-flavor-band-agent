"""Auto-clean chain precision tests (issue #58).

The auto-clean processing chain is float end-to-end; these tests assert the
file writes no longer quantize between steps: retained intermediates are
32-bit float WAV, the final output is a deliberate 24-bit PCM master, and the
choice is reported in the tool result. Standalone tool calls keep soundfile's
default subtype. No DB or LLM is touched (``BigFlavorMCPServer`` is
constructed but never ``initialize()``d) — the audio is a tiny synthetic take.
"""
import numpy as np
import pytest
import soundfile as sf

from src.production.big_flavor_mcp import (
    FINAL_WAV_SUBTYPE,
    INTERMEDIATE_WAV_SUBTYPE,
    BigFlavorMCPServer,
)

SR = 22050


@pytest.fixture()
def server():
    return BigFlavorMCPServer()


@pytest.fixture()
def raw_take(tmp_path):
    """~4.4s mono take: quiet noise lead-in/out around a 440 Hz tone."""
    rng = np.random.default_rng(58)
    lead = rng.normal(0, 0.001, int(0.7 * SR))
    t = np.arange(int(3 * SR)) / SR
    tone = 0.3 * np.sin(2 * np.pi * 440 * t) + rng.normal(0, 0.002, t.size)
    y = np.concatenate([lead, tone, lead]).astype(np.float32)
    path = tmp_path / "raw_take.wav"
    sf.write(str(path), y, SR, subtype="FLOAT")
    return path


async def test_auto_clean_float_intermediates_and_24bit_final(server, raw_take, tmp_path):
    output_path = tmp_path / "cleaned.wav"

    result = await server.auto_clean_recording(
        str(raw_take),
        str(output_path),
        keep_intermediates=True,
        steps_override={
            "trim": True,
            "noise_reduction": True,
            "eq": True,
            "normalize": True,
            "master": True,
        },
    )

    assert result["status"] == "success", result
    step_names = {s["step"] for s in result["steps_applied"]}
    assert {"trim", "noise_reduction", "eq", "normalize", "mastering"} <= step_names
    assert result["output_bit_depth"] == "24-bit PCM"

    # Final output: deliberate 24-bit PCM, not the 16-bit library default.
    assert sf.info(str(output_path)).subtype == FINAL_WAV_SUBTYPE

    # Every retained intermediate is full-precision float WAV and playable.
    step_dir = tmp_path / f"{output_path.stem}_steps"
    step_files = sorted(step_dir.glob("*.wav"))
    assert len(step_files) == 4, [f.name for f in step_files]
    for step_file in step_files:
        assert sf.info(str(step_file)).subtype == INTERMEDIATE_WAV_SUBTYPE, step_file.name
        data, sr = sf.read(str(step_file))
        assert len(data) > 0 and sr == SR


async def test_auto_clean_without_master_still_writes_24bit_final(server, raw_take, tmp_path):
    output_path = tmp_path / "cleaned_no_master.wav"

    result = await server.auto_clean_recording(
        str(raw_take),
        str(output_path),
        steps_override={
            "trim": False,
            "noise_reduction": False,
            "eq": False,
            "normalize": True,
            "master": False,
        },
    )

    assert result["status"] == "success", result
    assert result["output_bit_depth"] == "24-bit PCM"
    assert sf.info(str(output_path)).subtype == FINAL_WAV_SUBTYPE


async def test_standalone_normalize_keeps_default_subtype(server, raw_take, tmp_path):
    output_path = tmp_path / "normalized.wav"

    result = await server.normalize_audio(str(raw_take), -3.0, False, str(output_path))

    assert result["status"] == "success", result
    assert sf.info(str(output_path)).subtype == "PCM_16"
