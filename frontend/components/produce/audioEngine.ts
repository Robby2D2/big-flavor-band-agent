/**
 * Shared Web Audio helpers for the produce waveform editor (issue #70).
 *
 * One process-wide AudioContext backs both the full-mix waveform and the stem
 * mixer, so every stem played through it shares a single sample clock — that is
 * what keeps per-stem mute/solo/gain accurate and the stems in sync. No external
 * dependency (no wavesurfer.js): waveforms are decoded and drawn from the audio
 * itself.
 */

type WebkitWindow = Window & { webkitAudioContext?: typeof AudioContext };

let sharedContext: AudioContext | null = null;

/** Lazily create (and reuse) the single shared AudioContext. Browser only. */
export function getAudioContext(): AudioContext {
  if (typeof window === 'undefined') {
    throw new Error('AudioContext is only available in the browser');
  }
  if (!sharedContext) {
    const Ctor = window.AudioContext || (window as WebkitWindow).webkitAudioContext;
    if (!Ctor) {
      throw new Error('Web Audio API is not supported in this browser');
    }
    sharedContext = new Ctor();
  }
  return sharedContext;
}

/** Fetch and decode an audio URL into an AudioBuffer on the shared context. */
export async function decodeAudio(url: string): Promise<AudioBuffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load audio (${response.status})`);
  }
  const raw = await response.arrayBuffer();
  return getAudioContext().decodeAudioData(raw);
}

export interface Peaks {
  min: Float32Array;
  max: Float32Array;
  width: number;
}

/** The server's cached drawing envelope (src/production/waveform_peaks.py). */
export interface PeaksPayload {
  version: number;
  resolution: number;
  scale: number;
  duration_seconds: number;
  sample_rate: number;
  channels: number;
  min: number[];
  max: number[];
}

export interface WaveformPeaks {
  peaks: Peaks;
  /**
   * The source's true duration. Comes from the server rather than a decoded
   * buffer so waveforms and the transport work before any audio has arrived —
   * and so a lossy playback copy's few-ms drift never moves the timeline.
   */
  duration: number;
}

/**
 * Fetch a waveform envelope from the server and unpack it for drawing.
 *
 * Replaces decoding whole audio files client-side: the envelope is a few KB
 * against ~44MB for one uncompressed stem.
 */
export async function fetchPeaks(url: string): Promise<WaveformPeaks> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load waveform (${response.status})`);
  }
  const payload = (await response.json()).peaks as PeaksPayload;
  const width = payload.min.length;
  const min = new Float32Array(width);
  const max = new Float32Array(width);
  for (let i = 0; i < width; i++) {
    min[i] = payload.min[i] / payload.scale;
    max[i] = payload.max[i] / payload.scale;
  }
  return {
    peaks: { min, max, width },
    duration: payload.duration_seconds,
  };
}

/**
 * Resample a server envelope to an arbitrary canvas width.
 *
 * Downsampling takes the min of mins and max of maxes over each output pixel's
 * source range, which is exactly the envelope of the union — so peaks are never
 * softened by averaging. This runs on every resize, and at ~2000 source buckets
 * it costs a few thousand operations rather than the full-song sample scan the
 * old client-side implementation did.
 */
export function resamplePeaks(source: Peaks, width: number): Peaks {
  const safeWidth = Math.max(1, Math.floor(width));
  if (safeWidth === source.width) return source;

  const min = new Float32Array(safeWidth);
  const max = new Float32Array(safeWidth);
  const step = source.width / safeWidth;

  for (let i = 0; i < safeWidth; i++) {
    const start = Math.floor(i * step);
    const end = Math.min(source.width, Math.max(start + 1, Math.floor((i + 1) * step)));
    let lo = source.min[start];
    let hi = source.max[start];
    for (let j = start + 1; j < end; j++) {
      if (source.min[j] < lo) lo = source.min[j];
      if (source.max[j] > hi) hi = source.max[j];
    }
    min[i] = lo;
    max[i] = hi;
  }
  return { min, max, width: safeWidth };
}

export interface Region {
  start: number;
  end: number;
}

/** Format a seconds value as m:ss.d for the region/time readouts. */
export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00.0';
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}
