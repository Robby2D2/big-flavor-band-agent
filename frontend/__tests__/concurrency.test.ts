import { describe, expect, it } from 'vitest';
import { mapWithConcurrency } from '@/lib/concurrency';

describe('mapWithConcurrency', () => {
  it('keeps results in input order', async () => {
    const out = await mapWithConcurrency([1, 2, 3, 4, 5], 2, async (n) => n * 2);
    expect(out).toEqual([2, 4, 6, 8, 10]);
  });

  it('never runs more than `limit` jobs at once', async () => {
    let inFlight = 0;
    let peak = 0;
    const out = await mapWithConcurrency([1, 2, 3, 4, 5, 6], 2, async (n) => {
      inFlight++;
      peak = Math.max(peak, inFlight);
      await new Promise((resolve) => setTimeout(resolve, 1));
      inFlight--;
      return n;
    });
    expect(peak).toBe(2);
    expect(out).toEqual([1, 2, 3, 4, 5, 6]);
  });

  it('handles an empty batch', async () => {
    await expect(mapWithConcurrency([], 3, async (n) => n)).resolves.toEqual([]);
  });
});
