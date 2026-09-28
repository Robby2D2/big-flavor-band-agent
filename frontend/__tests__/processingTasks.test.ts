import { describe, expect, it } from 'vitest';

import {
  buildTasks,
  formatElapsed,
  summarizeTasks,
  TaskInput,
} from '@/lib/processingTasks';

const idle: TaskInput = {
  separation: null,
  analysis: null,
  render: { status: 'idle' },
  playback: null,
  now: 100_000,
};

const only = (input: Partial<TaskInput>) => buildTasks({ ...idle, ...input });

describe('buildTasks', () => {
  it('shows nothing when nothing is happening', () => {
    expect(buildTasks(idle)).toEqual([]);
  });

  it('times a separation, since Demucs reports no progress', () => {
    const [task] = only({ separation: { status: 'running', startedAt: 100_000 - 75_000 } });
    expect(task.title).toBe('Separating into stems');
    expect(task.detail).toContain('1m 15s');
    expect(task.cancelLabel).toBe('Cancel');
  });

  it('says a cancelled separation keeps working on the GPU', () => {
    const [task] = only({ separation: { status: 'cancelled', startedAt: 0 } });
    expect(task.state).toBe('cancelled');
    expect(task.note).toMatch(/background/);
    expect(task.cancelLabel).toBeUndefined();
  });

  it('counts analysis checks across the parts and names the one in progress', () => {
    const [task] = only({
      analysis: {
        status: 'running',
        rows: [
          { label: 'Full mix', done: 3, total: 3 },
          { label: 'vocals', done: 2, total: 5 },
          { label: 'drums', done: 0, total: 4 },
        ],
      },
    });
    expect(task.done).toBe(5);
    expect(task.total).toBe(12);
    expect(task.detail).toBe('1 of 3 parts measured · vocals 2/5');
  });

  it('keeps what a cancelled analysis already measured', () => {
    const [task] = only({
      analysis: {
        status: 'cancelled',
        rows: [
          { label: 'vocals', done: 5, total: 5 },
          { label: 'drums', done: 1, total: 4 },
        ],
      },
    });
    expect(task.detail).toContain('1 part already measured');
  });

  it('narrates a render step by step', () => {
    const [task] = only({
      render: {
        status: 'running',
        preview: true,
        fix_count: 21,
        progress: {
          stage: 'stems', stem: 'drums', tool: 'reduce_noise',
          done: 9, total: 21, stems_done: 4, stems_total: 7,
        },
      },
    });
    expect(task.title).toBe('Rendering fixes');
    expect(task.detail).toBe('drums: reduce noise · 3 stems left');
    expect([task.done, task.total]).toEqual([9, 21]);
    expect(task.cancelLabel).toBe('Cancel');
  });

  it('will not offer to cancel once the version is being written', () => {
    const [task] = only({
      render: { status: 'running', preview: false, progress: { stage: 'saving', done: 21, total: 21 } },
    });
    expect(task.cancelLabel).toBeNull();
    expect(task.detail).toBe('Writing the new version');
  });

  it('says a save waiting on a render will follow it', () => {
    const [task] = only({
      render: { status: 'running', preview: false, progress: { stage: 'stems', done: 2, total: 21 } },
    });
    expect(task.title).toBe('Saving new version');
    expect(task.cancelLabel).toBe('Cancel save');
    expect(task.note).toMatch(/Saves the moment/);
  });

  it('reports a reused render as nothing redone', () => {
    const [task] = only({ render: { status: 'complete', preview: true, reused: true } });
    expect(task.state).toBe('done');
    expect(task.detail).toMatch(/nothing had to be redone/);
  });

  it('carries the notices of fixes that did less than claimed (PROD-09)', () => {
    const notices = [{ scope: 'vocals', tool: 'correct_pitch', reason: 'whole-file shift' }];
    const [task] = only({ render: { status: 'complete', preview: false, version: null, notices } });
    expect(task.title).toBe('Saved as a new version');
    expect(task.notices).toEqual(notices);
  });

  it('says what a cancelled render left behind', () => {
    const [task] = only({ render: { status: 'cancelled', preview: true } });
    expect(task.detail).toMatch(/kept for next time/);
  });

  it('shows the error of a failed render', () => {
    const [task] = only({ render: { status: 'failed', error: 'Stem 7 not found' } });
    expect(task.state).toBe('failed');
    expect(task.detail).toBe('Stem 7 not found');
  });

  it('lists rows rendering for playback after a change, and that the original plays meanwhile', () => {
    const [task] = only({
      playback: { rows: ['vocals', 'drums'], done: 1, total: 3, afterRender: false },
    });
    expect(task.title).toBe('Rendering fixes to play');
    expect(task.detail).toBe('1 of 3 stems · vocals, drums');
    expect(task.note).toMatch(/original audio/);
    expect(task.cancelLabel).toBe('Play without');
  });

  it('shows loading a finished render as that render, not a second task', () => {
    // The owner saw "Fixes rendered" then "Rendering fixes to play" and asked
    // what the difference was. There is none: it is one render being loaded.
    const tasks = only({
      render: { status: 'complete', preview: true },
      playback: { rows: ['drums'], done: 4, total: 7, afterRender: true },
    });
    expect(tasks).toHaveLength(1);
    expect(tasks[0].title).toBe('Rendering fixes');
    expect(tasks[0].state).toBe('running');
    expect(tasks[0].detail).toBe('Loading playback · 4 of 7 stems');
    expect(tasks[0].cancelLabel).toBe('Play without');
  });

  it('narrates the server making playback copies as the last step', () => {
    const [task] = only({
      render: {
        status: 'running',
        preview: true,
        progress: { stage: 'playback', done: 21, total: 21, playback_done: 2, playback_total: 7 },
      },
    });
    expect(task.detail).toBe('Preparing playback · 2 of 7 stems');
  });

  it('orders tasks the way the work happens', () => {
    const tasks = buildTasks({
      ...idle,
      separation: { status: 'running', startedAt: 0 },
      analysis: { status: 'running', rows: [] },
      render: { status: 'running', preview: true },
      playback: { rows: ['vocals'], done: 0, total: 1, afterRender: false },
    });
    expect(tasks.map((t) => t.id)).toEqual(['separate', 'analyze', 'render', 'playback']);
  });
});

describe('summarizeTasks', () => {
  it('counts the first running task', () => {
    const tasks = only({
      render: { status: 'running', preview: true, progress: { stage: 'stems', done: 9, total: 21 } },
    });
    expect(summarizeTasks(tasks)).toBe('Rendering fixes · 9/21');
  });

  it('falls back to the last outcome when nothing runs', () => {
    expect(summarizeTasks(only({ render: { status: 'complete', preview: true } }))).toBe(
      'Fixes rendered'
    );
  });
});

describe('formatElapsed', () => {
  it('reads as seconds, then minutes', () => {
    expect(formatElapsed(42_000)).toBe('42s');
    expect(formatElapsed(125_000)).toBe('2m 05s');
  });
});
