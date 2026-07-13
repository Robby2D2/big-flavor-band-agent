"""Demucs stem separation and stem-remix downmix (issue #67).

Splits a song's audio into independently editable/streamable stems (vocals,
drums, bass, guitar, other) with Demucs, and recombines a stem set — with
per-stem gain/mute — back into a single candidate file that enters the existing
``/produce`` audition -> approve -> version flow.

Both operations are pure/CPU-bound (Demucs inference, numpy mixing, file writes),
so callers run them off the FastAPI event loop via a threadpool. Demucs runs on
CPU by default and uses the GPU automatically when one is available — CPU is the
correctness path, GPU only makes it faster. Nothing here mutates catalog
originals or existing versions: inputs are read-only, every output is a fresh
file under ``produced/``.
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("backend-api")

# Default Demucs model: the 6-source variant so guitar/piano are separated in
# addition to vocals/drums/bass/other, matching the spec's stem list.
DEFAULT_MODEL = "htdemucs_6s"


def _select_device() -> str:
    """Pick a compute device: CUDA GPU if present, else CPU (the correctness path)."""
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def separate_stems(
    source_path: str,
    output_dir: str,
    model_name: str = DEFAULT_MODEL,
) -> List[Dict[str, str]]:
    """Separate ``source_path`` into stem WAV files under ``output_dir``.

    Runs Demucs' pretrained model over the input and writes one WAV per source
    (vocals, drums, bass, guitar, other, ...) as ``{output_dir}/{name}.wav``.
    Synchronous/CPU-bound — run off the event loop. Returns a list of
    ``{"name", "path"}`` for the stems written. Raises on failure so the caller
    can mark the job failed.
    """
    import torch
    import torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    device = _select_device()
    logger.info("Stem separation: model=%s device=%s src=%s", model_name, device, source_path)

    model = get_model(model_name)
    model.to(device)
    model.eval()

    # Load to the model's sample rate as stereo, shaped (channels, samples).
    wav, sr = torchaudio.load(source_path)
    if sr != model.samplerate:
        wav = torchaudio.functional.resample(wav, sr, model.samplerate)
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)  # Demucs expects stereo input.

    # apply_model wants a batch dimension: (batch, channels, samples).
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)
    with torch.no_grad():
        sources = apply_model(model, wav[None], device=device)[0]
    sources = sources * ref.std() + ref.mean()

    stems: List[Dict[str, str]] = []
    for source_tensor, name in zip(sources, model.sources):
        stem_path = out / f"{name}.wav"
        torchaudio.save(str(stem_path), source_tensor.cpu(), model.samplerate)
        stems.append({"name": name, "path": str(stem_path)})

    logger.info("Stem separation complete: %d stems in %s", len(stems), output_dir)
    return stems


def remix_stems(
    stems: List[Dict[str, str]],
    output_path: str,
    adjustments: Optional[Dict[str, Dict[str, object]]] = None,
) -> str:
    """Mix a stem set back down to a single WAV, honouring per-stem gain/mute.

    ``stems`` is the list of ``{"name", "path"}`` for a stem set. ``adjustments``
    maps a stem name to ``{"gain": float, "mute": bool}`` (gain is a linear
    multiplier, default 1.0; muted stems contribute nothing). Sums the stems
    sample-aligned and writes ``output_path``. Synchronous/CPU-bound — run off
    the event loop. Returns ``output_path``. Raises if no stem contributes audio.
    """
    import numpy as np
    import soundfile as sf

    adjustments = adjustments or {}

    mix = None
    sr = None
    for stem in stems:
        name = stem["name"]
        adjust = adjustments.get(name, {})
        if adjust.get("mute"):
            continue
        gain = float(adjust.get("gain", 1.0))
        if gain == 0.0:
            continue

        data, stem_sr = sf.read(stem["path"], always_2d=True)  # (samples, channels)
        if sr is None:
            sr = stem_sr
        elif stem_sr != sr:
            raise ValueError(
                f"Stem '{name}' sample rate {stem_sr} != mix rate {sr}"
            )

        contribution = data.astype(np.float64) * gain
        if mix is None:
            mix = contribution
        else:
            # Stems from one separation share length/channels, but guard anyway.
            frames = min(mix.shape[0], contribution.shape[0])
            channels = min(mix.shape[1], contribution.shape[1])
            mix = mix[:frames, :channels] + contribution[:frames, :channels]

    if mix is None or sr is None:
        raise ValueError("No stems contribute audio to the remix (all muted or gain 0)")

    # Prevent clipping from summed stems while preserving relative balance.
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1.0:
        mix = mix / peak

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), mix.astype(np.float32), sr)
    logger.info("Stem remix written: %s", output_path)
    return output_path
