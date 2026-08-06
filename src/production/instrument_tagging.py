"""Instrument tagging for separated stems.

Demucs splits a song into a *fixed* set of sources — ``htdemucs_6s`` gives
vocals/drums/bass/guitar/piano/other and nothing else, because the source list
is baked into the model weights. A banjo, mandolin or fiddle isn't lost (the
stems still sum back to the mix), it just lands in ``other``, or bleeds into
``guitar``. The gap is naming, not coverage.

So rather than trying to separate instruments the model was never trained on,
this module *labels* what is actually in each stem with an AudioSet audio
tagger, and reports when a stem came back effectively empty — a band with no
piano still gets a ``piano`` stem out of Demucs, and it's useful to say so.

Pure/CPU-bound (model inference over a whole file), so callers run it off the
FastAPI event loop via a threadpool. Read-only: nothing here writes audio.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.production.stem_separation import select_device

logger = logging.getLogger("backend-api")

# AudioSet-trained Audio Spectrogram Transformer. Multi-label over 527 classes,
# which is what lets one stem report "banjo *and* fiddle" instead of a single
# winner.
DEFAULT_MODEL = "MIT/ast-finetuned-audioset-10-10-0.4593"

SAMPLE_RATE = 16000
WINDOW_SECONDS = 10.0
# Enough windows to catch an instrument that only plays one section (a banjo
# break in the bridge), few enough to stay quick on a whole song.
MAX_WINDOWS = 8
# Below this RMS a window is silence — scoring it just dilutes the result, and
# for an empty Demucs stem *every* window is like this.
SILENCE_RMS = 1e-4

# Whole-stem silence is judged on *peak*, not RMS. An empty Demucs stem is never
# digital silence, it's low-level bleed, and measured across real separations
# those peak around -56..-52 dBFS while the quietest genuinely-present
# instrument peaks at -23 dBFS. RMS can't make that call: a sparse real part (a
# piano hit a few times in a song) measured -54.7 dBFS RMS, within 6 dB of an
# empty stem, while its peak stayed ~30 dB clear. -40 dBFS sits in the middle of
# that gap with wide margin on both sides.
SILENCE_PEAK = 0.01
MIN_SCORE = 0.10
MAX_LABELS = 4

# AudioSet display names are comma-separated alias lists ("Violin, fiddle"), so
# the vocabulary is keyed by individual lowercased alias. Several AudioSet
# classes can map to one producer-facing name (the three organ classes); the
# highest-scoring of them wins. Anything not listed here is ignored — the point
# is to name instruments a producer would recognise on a stem, not to surface
# all 527 AudioSet classes.
INSTRUMENT_VOCAB: Dict[str, str] = {
    # The ones Demucs can't separate, which is the whole reason this exists.
    "banjo": "Banjo",
    "mandolin": "Mandolin",
    "ukulele": "Ukulele",
    "zither": "Zither",
    "sitar": "Sitar",
    "violin": "Fiddle / violin",
    "fiddle": "Fiddle / violin",
    "cello": "Cello",
    "double bass": "Double bass",
    "harmonica": "Harmonica",
    "accordion": "Accordion",
    "bagpipes": "Bagpipes",
    "steel guitar": "Steel / slide guitar",
    "slide guitar": "Steel / slide guitar",
    # Instruments Demucs does separate — still worth confirming, since this is
    # how bleed shows up (a mandolin scoring on the "guitar" stem).
    "acoustic guitar": "Acoustic guitar",
    "electric guitar": "Electric guitar",
    "bass guitar": "Bass guitar",
    "guitar": "Guitar",
    "piano": "Piano",
    "electric piano": "Electric piano",
    "organ": "Organ",
    "electronic organ": "Organ",
    "hammond organ": "Organ",
    "harpsichord": "Harpsichord",
    "synthesizer": "Synthesizer",
    "drum kit": "Drum kit",
    "snare drum": "Snare drum",
    "bass drum": "Bass drum",
    "hi-hat": "Hi-hat",
    "cymbal": "Cymbal",
    "tambourine": "Tambourine",
    "percussion": "Percussion",
    "trumpet": "Trumpet",
    "trombone": "Trombone",
    "saxophone": "Saxophone",
    "flute": "Flute",
    "clarinet": "Clarinet",
    "french horn": "French horn",
    "singing": "Vocal",
    "male singing": "Male vocal",
    "female singing": "Female vocal",
    "choir": "Choir",
    "rapping": "Rapping",
    "whistling": "Whistling",
    "humming": "Humming",
}

# model_name -> (feature_extractor, model, {class_index: friendly_name}). Loading
# the checkpoint is the expensive part; tagging a whole stem set would otherwise
# pay it once per stem.
_CACHE: Dict[str, Tuple[Any, Any, Dict[int, str]]] = {}


def build_label_index(id2label: Dict[int, str]) -> Dict[int, str]:
    """Map a model's class indices to producer-facing instrument names.

    Splits each AudioSet display name on commas so "Violin, fiddle" matches on
    either alias, and keeps only classes present in ``INSTRUMENT_VOCAB``.
    """
    index: Dict[int, str] = {}
    for class_index, display in id2label.items():
        for alias in display.split(","):
            friendly = INSTRUMENT_VOCAB.get(alias.strip().lower())
            if friendly:
                index[int(class_index)] = friendly
                break
    return index


def summarize_scores(
    scores_by_index: Dict[int, float],
    label_index: Dict[int, str],
    min_score: float = MIN_SCORE,
    max_labels: int = MAX_LABELS,
) -> List[Dict[str, Any]]:
    """Reduce raw per-class scores to a ranked list of named instruments.

    Several AudioSet classes can share one producer-facing name, so scores are
    collapsed by taking the strongest class for each name. Kept as its own pure
    function so the vocabulary/threshold behaviour is testable without loading
    a model.
    """
    best: Dict[str, float] = {}
    for class_index, score in scores_by_index.items():
        friendly = label_index.get(class_index)
        if friendly is None or score < min_score:
            continue
        if score > best.get(friendly, 0.0):
            best[friendly] = score

    ranked = sorted(best.items(), key=lambda pair: pair[1], reverse=True)
    return [
        {"label": label, "score": round(float(score), 3)}
        for label, score in ranked[:max_labels]
    ]


def _load(model_name: str) -> Tuple[Any, Any, Dict[int, str]]:
    """Load (and cache) the tagger, plus its class-index -> instrument map."""
    cached = _CACHE.get(model_name)
    if cached is not None:
        return cached

    from transformers import AutoFeatureExtractor, AutoModelForAudioClassification

    logger.info("Loading instrument tagger: %s", model_name)
    extractor = AutoFeatureExtractor.from_pretrained(model_name)
    model = AutoModelForAudioClassification.from_pretrained(model_name)
    model.to(select_device())
    model.eval()

    label_index = build_label_index(model.config.id2label)
    if not label_index:
        raise RuntimeError(
            f"Instrument tagger {model_name} exposes no labels in INSTRUMENT_VOCAB — "
            "its class names don't look like AudioSet display names"
        )
    logger.info("Instrument tagger ready: %d taggable classes", len(label_index))

    _CACHE[model_name] = (extractor, model, label_index)
    return _CACHE[model_name]


def is_silent(samples: Any) -> bool:
    """Whether a clip is an *empty* stem rather than merely a quiet one.

    The distinction the console depends on: an empty stem is hidden entirely, so
    calling a real-but-sparse instrument silent would make it disappear. Judged
    on peak for the reason given at ``SILENCE_PEAK``. Kept as its own pure
    function so the threshold behaviour is testable without loading a model.
    """
    import numpy as np

    if samples.size == 0:
        return True
    return float(np.abs(samples).max()) < SILENCE_PEAK


def _windows(samples: Any, window_length: int) -> List[Any]:
    """Evenly spaced non-silent windows across a clip, in file order."""
    import numpy as np

    if len(samples) <= window_length:
        return [samples] if float(np.sqrt(np.mean(samples**2))) > SILENCE_RMS else []

    starts = np.linspace(0, len(samples) - window_length, MAX_WINDOWS).astype(int)
    picked = []
    for start in starts:
        window = samples[start : start + window_length]
        if float(np.sqrt(np.mean(window**2))) > SILENCE_RMS:
            picked.append(window)
    return picked


def identify_instruments(
    audio_path: str,
    model_name: str = DEFAULT_MODEL,
    min_score: float = MIN_SCORE,
    max_labels: int = MAX_LABELS,
) -> Dict[str, Any]:
    """Tag the instruments audible in one audio file.

    Returns ``{"instruments": [{"label", "score"}, ...], "silent": bool,
    "model": str}``. ``silent`` is true when every window is below the noise
    floor — a real answer for a Demucs stem of an instrument the band doesn't
    play, not a failure. Synchronous/CPU-bound: run off the event loop. Raises
    if the model or the audio can't be loaded, so the caller can decide whether
    that's fatal.
    """
    import librosa
    import numpy as np
    import torch

    extractor, model, label_index = _load(model_name)

    samples, _ = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)
    # Checked before windowing: an empty stem's bleed is loud enough to clear
    # the per-window RMS gate below, so without this the tagger scores noise and
    # reports the stem as present-but-unrecognised.
    if is_silent(samples):
        logger.info("Instrument tagging: %s is silent", audio_path)
        return {"instruments": [], "silent": True, "model": model_name}

    windows = _windows(samples, int(WINDOW_SECONDS * SAMPLE_RATE))
    if not windows:
        logger.info("Instrument tagging: %s is silent", audio_path)
        return {"instruments": [], "silent": True, "model": model_name}

    device = select_device()
    inputs = extractor(
        [w for w in windows], sampling_rate=SAMPLE_RATE, return_tensors="pt"
    )
    with torch.no_grad():
        logits = model(**{k: v.to(device) for k, v in inputs.items()}).logits
    # Multi-label head: sigmoid per class, then the strongest window per class —
    # an instrument that only plays one section should still be reported, which
    # averaging across windows would wash out.
    scores = torch.sigmoid(logits).max(dim=0).values.cpu().numpy()

    instruments = summarize_scores(
        {i: float(s) for i, s in enumerate(scores)},
        label_index,
        min_score=min_score,
        max_labels=max_labels,
    )
    logger.info(
        "Instrument tagging: %s -> %s",
        audio_path,
        ", ".join(i["label"] for i in instruments) or "nothing above threshold",
    )
    return {"instruments": instruments, "silent": False, "model": model_name}


def summarize_for_display(tags: Optional[Dict[str, Any]]) -> str:
    """One-line rendering of a tag payload, for logs and the API."""
    if not tags:
        return "not identified"
    if tags.get("silent"):
        return "silent"
    labels = [i["label"] for i in tags.get("instruments", [])]
    return " · ".join(labels) if labels else "nothing recognised"
