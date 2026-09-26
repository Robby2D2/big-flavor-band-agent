"""Reading recording-session audio, which ``soundfile`` cannot open.

Reaper records to **WavPack** (``.wv``). libsndfile has no WavPack decoder, so
neither ``soundfile`` nor ``librosa`` — and therefore none of the audio tools in
this package — can read a session's tracks directly. ffmpeg is already in the
backend image and decodes WavPack, so it is the seam.

This module is deliberately the *only* place that knows session audio is not
plain PCM. Everything downstream works on the WAV/FLAC files written here, so
the existing tools, peak computation and previews need no changes.
"""
from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger("backend-api")

#: Envelope sample rate. The envelope answers "is anyone playing", which needs
#: no fidelity — and decoding at 8 kHz runs at roughly 775x realtime, so a
#: whole session scans in about a minute.
ENVELOPE_RATE = 8000

#: Envelope frames per second. 20 puts take boundaries within 50ms, far finer
#: than the multi-second silences that separate takes.
ENVELOPE_FPS = 20


class DecodeError(RuntimeError):
    """ffmpeg could not read a file."""


@dataclass
class AudioInfo:
    sample_rate: int
    channels: int
    duration: float
    codec: str


@dataclass
class Envelope:
    """Per-frame loudness of one track, used to find where the band is playing."""

    #: RMS per frame, linear.
    rms: np.ndarray
    #: Absolute peak per frame, linear.
    peak: np.ndarray
    fps: int

    def __len__(self) -> int:
        return len(self.rms)

    @property
    def duration(self) -> float:
        return len(self.rms) / self.fps


def probe(path: str | Path) -> AudioInfo:
    """Read a file's format without decoding it."""
    result = _run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
            "-of", "json",
            str(path),
        ]
    )
    try:
        payload = json.loads(result)
        stream = payload["streams"][0]
        return AudioInfo(
            sample_rate=int(stream["sample_rate"]),
            channels=int(stream["channels"]),
            duration=float(payload["format"]["duration"]),
            codec=stream["codec_name"],
        )
    except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
        raise DecodeError(f"Could not probe {path}: {exc}") from exc


def envelope(path: str | Path, fps: int = ENVELOPE_FPS) -> Envelope:
    """Compute a track's loudness envelope.

    Decodes to 8 kHz mono and reduces each frame to its RMS and peak as the
    samples stream in, so a 48-minute 24-bit track costs a few megabytes of
    memory rather than a few hundred.
    """
    samples_per_frame = ENVELOPE_RATE // fps
    command = [
        "ffmpeg", "-v", "error",
        "-i", str(path),
        "-ac", "1",
        "-ar", str(ENVELOPE_RATE),
        "-f", "f32le",
        "-",
    ]

    rms: List[float] = []
    peak: List[float] = []
    leftover = np.empty(0, dtype=np.float32)
    # Whole frames only, so a read never splits one across chunks.
    chunk_bytes = samples_per_frame * 4 * 256

    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert process.stdout is not None
    try:
        while True:
            chunk = process.stdout.read(chunk_bytes)
            if not chunk:
                break
            block = np.concatenate(
                [leftover, np.frombuffer(chunk, dtype=np.float32)]
            )
            whole = len(block) // samples_per_frame
            if whole:
                frames = block[: whole * samples_per_frame].reshape(
                    whole, samples_per_frame
                )
                rms.extend(np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1)))
                peak.extend(np.max(np.abs(frames), axis=1))
            leftover = block[whole * samples_per_frame :]
    finally:
        process.stdout.close()
        stderr = process.stderr.read() if process.stderr else b""
        if process.stderr:
            process.stderr.close()
        code = process.wait()

    if code != 0:
        raise DecodeError(
            f"ffmpeg failed on {path}: {stderr.decode('utf-8', 'replace').strip()}"
        )

    return Envelope(
        rms=np.asarray(rms, dtype=np.float32),
        peak=np.asarray(peak, dtype=np.float32),
        fps=fps,
    )


def extract_segment(
    source: str | Path,
    output_path: str | Path,
    start: float,
    duration: float,
    sample_rate: Optional[int] = None,
    channels: Optional[int] = None,
) -> str:
    """Decode one time range of a session track into a normal PCM file.

    The output format follows ``output_path``'s extension — FLAC for take stems
    we keep, WAV where a tool wants uncompressed input. Either way the result is
    something ``soundfile`` can open, which is the point.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # 24-bit either way: the sources are 24-bit, and FLAC stores that losslessly
    # in roughly half the space, which is why kept stems use it.
    if output.suffix == ".wav":
        codec = ["-c:a", "pcm_s24le"]
    else:
        codec = ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"]

    command = [
        "ffmpeg", "-v", "error", "-y",
        # Seeking before -i is the fast path; WavPack is seekable so this stays
        # exact rather than snapping to a keyframe.
        "-ss", f"{start:.6f}",
        "-t", f"{duration:.6f}",
        "-i", str(source),
        *codec,
    ]
    if sample_rate:
        command += ["-ar", str(sample_rate)]
    if channels:
        command += ["-ac", str(channels)]
    command.append(str(output))
    _run(command)
    return str(output)


def _run(command: List[str]) -> str:
    """Run an ffmpeg/ffprobe command, raising with its stderr on failure."""
    try:
        completed = subprocess.run(
            command, capture_output=True, check=True, text=True
        )
    except FileNotFoundError as exc:
        raise DecodeError(
            f"{command[0]} not found — session audio needs ffmpeg on PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise DecodeError(
            f"{command[0]} failed: {(exc.stderr or '').strip()}"
        ) from exc
    return completed.stdout
