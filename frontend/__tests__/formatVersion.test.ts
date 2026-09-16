import { describe, expect, it } from 'vitest';
import {
  formatBytes,
  formatDuration,
  formatProducedAt,
  formatSteps,
} from '@/lib/formatVersion';

describe('formatBytes', () => {
  it('shows raw bytes below a kilobyte', () => {
    expect(formatBytes(512)).toBe('512 B');
  });

  it('steps up through the units', () => {
    expect(formatBytes(5_347_737)).toBe('5.1 MB');
    expect(formatBytes(2048)).toBe('2.0 KB');
    expect(formatBytes(3 * 1024 ** 3)).toBe('3.0 GB');
  });

  it('stops at GB rather than inventing a unit', () => {
    expect(formatBytes(5 * 1024 ** 4)).toContain('GB');
  });

  it('has a dash for unknown', () => {
    expect(formatBytes(null)).toBe('—');
    expect(formatBytes(undefined)).toBe('—');
  });

  it('treats zero as a real size, not unknown', () => {
    expect(formatBytes(0)).toBe('0 B');
  });
});

describe('formatDuration', () => {
  it('pads the seconds', () => {
    expect(formatDuration(222)).toBe('3:42');
    expect(formatDuration(65)).toBe('1:05');
  });

  it('rolls a rounded-up 60 into the next minute instead of reading 3:60', () => {
    expect(formatDuration(239.6)).toBe('4:00');
  });

  it('has a dash for unknown', () => {
    expect(formatDuration(null)).toBe('—');
  });

  it('treats zero as a real duration', () => {
    expect(formatDuration(0)).toBe('0:00');
  });
});

describe('formatProducedAt', () => {
  it('has a dash for missing or unparseable dates', () => {
    expect(formatProducedAt(null)).toBe('—');
    expect(formatProducedAt('')).toBe('—');
    expect(formatProducedAt('not a date')).toBe('—');
  });

  it('renders a real date', () => {
    expect(formatProducedAt('2026-09-16T14:05:39Z')).not.toBe('—');
  });
});

describe('formatSteps', () => {
  it('joins whole-mix steps', () => {
    expect(formatSteps([{ step: 'denoise' }, { step: 'master' }])).toBe('denoise, master');
  });

  it('reads the per-stem shape, which used to render "undefined"', () => {
    // accept-fixes writes {stem, tools}; only .step was ever read.
    expect(
      formatSteps([{ stem: 44, tools: ['apply_eq', 'correct_beats'] }])
    ).toBe('apply_eq, correct_beats');
  });

  it('handles both shapes in the same array, because both are written', () => {
    expect(
      formatSteps([
        { stem: 44, tools: ['apply_eq'] },
        { step: 'normalize_audio', scope: 'master' } as never,
      ])
    ).toBe('apply_eq, normalize_audio');
  });

  it('names a tool once however many stems it was applied to', () => {
    expect(
      formatSteps([
        { stem: 1, tools: ['apply_eq', 'reduce_noise'] },
        { stem: 2, tools: ['apply_eq'] },
        { stem: 3, tools: ['apply_eq'] },
      ])
    ).toBe('apply_eq, reduce_noise');
  });

  it('has a dash for none', () => {
    expect(formatSteps([])).toBe('—');
    expect(formatSteps(null)).toBe('—');
  });

  it('has a dash for entries that carry no tool at all', () => {
    expect(formatSteps([{ stem: 44, tools: [] }])).toBe('—');
    expect(formatSteps([{} as never])).toBe('—');
  });
});
