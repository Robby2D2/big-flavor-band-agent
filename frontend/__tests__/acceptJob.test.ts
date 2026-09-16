import { describe, expect, it } from 'vitest';
import { describeAcceptJob } from '@/hooks/useAcceptJob';

describe('describeAcceptJob', () => {
  it('says nothing when nothing is happening', () => {
    expect(describeAcceptJob({ status: 'idle' })).toBeNull();
  });

  it('says nothing once a render has completed', () => {
    // The finished version is in the list by then — a lingering row would just
    // duplicate it.
    expect(describeAcceptJob({ status: 'complete', version: null })).toBeNull();
  });

  it('announces a save in progress', () => {
    const notice = describeAcceptJob({ status: 'running', preview: false, fix_count: 17 });

    expect(notice?.label).toBe('Saving new version…');
    expect(notice?.detail).toContain('17 fixes');
    expect(notice?.tone).toBe('progress');
  });

  it('distinguishes a preview render from a save', () => {
    const notice = describeAcceptJob({ status: 'running', preview: true, fix_count: 4 });
    expect(notice?.label).toBe('Rendering preview…');
  });

  it('counts a single fix in the singular', () => {
    const notice = describeAcceptJob({ status: 'running', preview: false, fix_count: 1 });
    expect(notice?.detail).toContain('1 fix ');
    expect(notice?.detail).not.toContain('1 fixes');
  });

  it('copes with a missing fix count', () => {
    expect(describeAcceptJob({ status: 'running' })?.detail).toContain('0 fixes');
  });

  it('surfaces a failure with its reason', () => {
    const notice = describeAcceptJob({ status: 'failed', error: 'Stem 7 not found' });

    expect(notice?.label).toBe('Render failed');
    expect(notice?.detail).toBe('Stem 7 not found');
    expect(notice?.tone).toBe('error');
  });

  it('still explains a failure with no reason attached', () => {
    expect(describeAcceptJob({ status: 'failed' })?.detail).toBeTruthy();
  });
});
