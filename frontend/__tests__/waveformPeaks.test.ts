import { describe, expect, it } from 'vitest';
import { Peaks, resamplePeaks } from '@/components/produce/audioEngine';

/** Build a Peaks envelope from plain arrays, the way fetchPeaks does. */
function makePeaks(min: number[], max: number[]): Peaks {
  return { min: Float32Array.from(min), max: Float32Array.from(max), width: min.length };
}

/** A 2000-bucket envelope with a single spike, mirroring the server's output. */
function envelopeWithSpike(spikeAt: number, width = 2000): Peaks {
  const min = new Array(width).fill(-0.1);
  const max = new Array(width).fill(0.1);
  min[spikeAt] = -0.95;
  max[spikeAt] = 0.9;
  return makePeaks(min, max);
}

describe('resamplePeaks', () => {
  it('returns the source untouched when the width already matches', () => {
    const source = envelopeWithSpike(500);
    expect(resamplePeaks(source, source.width)).toBe(source);
  });

  it('downsamples to the requested width', () => {
    const resampled = resamplePeaks(envelopeWithSpike(500), 144);
    expect(resampled.width).toBe(144);
    expect(resampled.min).toHaveLength(144);
    expect(resampled.max).toHaveLength(144);
  });

  it('preserves the extremes when downsampling', () => {
    // The whole point of min-of-mins / max-of-maxes: a transient must survive
    // being squeezed into a 144px sparkline rather than being averaged away.
    const resampled = resamplePeaks(envelopeWithSpike(500), 144);
    expect(Math.min(...resampled.min)).toBeCloseTo(-0.95, 5);
    expect(Math.max(...resampled.max)).toBeCloseTo(0.9, 5);
  });

  it('keeps a spike in the bucket it belongs to', () => {
    // Bucket 500 of 2000 is a quarter of the way in, so at width 100 the spike
    // should land in bucket 25 — not smeared across neighbours.
    const resampled = resamplePeaks(envelopeWithSpike(500), 100);
    expect(resampled.max[25]).toBeCloseTo(0.9, 5);
    expect(resampled.max[24]).toBeCloseTo(0.1, 5);
    expect(resampled.max[26]).toBeCloseTo(0.1, 5);
  });

  it('upsamples without dropping or duplicating the envelope bounds', () => {
    const source = makePeaks([-0.2, -0.6, -0.1], [0.3, 0.7, 0.2]);
    const resampled = resamplePeaks(source, 12);
    expect(resampled.width).toBe(12);
    expect(Math.max(...resampled.max)).toBeCloseTo(0.7, 5);
    expect(Math.min(...resampled.min)).toBeCloseTo(-0.6, 5);
  });

  it('never emits an empty bucket when widths do not divide evenly', () => {
    // 2000 -> 300 leaves a fractional step; every output pixel must still read
    // at least one source bucket or the waveform would show gaps.
    const resampled = resamplePeaks(envelopeWithSpike(1234), 300);
    expect(resampled.width).toBe(300);
    expect(Array.from(resampled.max).every((v) => Number.isFinite(v))).toBe(true);
    expect(Array.from(resampled.min).every((v) => Number.isFinite(v))).toBe(true);
  });

  it('clamps a zero or negative width to a single bucket', () => {
    expect(resamplePeaks(envelopeWithSpike(10), 0).width).toBe(1);
  });
});
