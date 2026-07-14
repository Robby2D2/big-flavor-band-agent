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

/**
 * Reduce an AudioBuffer's first channel to per-pixel min/max peaks for drawing.
 * Cheap enough to run on the client for a full song at typical widths.
 */
export function computePeaks(buffer: AudioBuffer, width: number): Peaks {
  const safeWidth = Math.max(1, Math.floor(width));
  const data = buffer.getChannelData(0);
  const total = data.length;
  const min = new Float32Array(safeWidth);
  const max = new Float32Array(safeWidth);
  const step = total / safeWidth;

  for (let i = 0; i < safeWidth; i++) {
    const start = Math.floor(i * step);
    const end = Math.min(total, Math.floor((i + 1) * step));
    let lo = 1.0;
    let hi = -1.0;
    for (let j = start; j < end; j++) {
      const v = data[j];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    if (end <= start) {
      lo = 0;
      hi = 0;
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
