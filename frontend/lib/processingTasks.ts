/**
 * What the task panel says about the work in flight on the produce page.
 *
 * Four kinds of work can be running after Start analysis, each owned by a
 * different piece of state: separating stems (a server job, polled), measuring
 * them (requests from this page), rendering the fixes (a server job with
 * step-by-step progress), and rendering a row's fixes so it can be played. This
 * module turns those into one list of tasks the panel draws, and it is pure so
 * every wording and count can be tested without a DOM.
 *
 * Cancelling is part of the contract (PROD-19): each running task says what its
 * cancel button does, and a task that keeps working in the background after a
 * cancel says so rather than pretending it stopped.
 */
import type { AcceptJob, FixNotice } from '@/hooks/useAcceptJob';

export type TaskState = 'running' | 'done' | 'failed' | 'cancelled';
export type TaskId = 'separate' | 'analyze' | 'render' | 'playback';

/** One part's share of a task: a stem's checks, say. */
export interface TaskRow {
  label: string;
  done: number;
  total: number;
}

export interface Task {
  id: TaskId;
  title: string;
  /** What is happening right now, in a line. */
  detail: string;
  state: TaskState;
  /** Drives the progress bar; absent when the work cannot be counted. */
  done?: number;
  total?: number;
  rows?: TaskRow[];
  /** The cancel button's label, or null when this task cannot be stopped now. */
  cancelLabel?: string | null;
  /** A second line, for what the producer must know about the outcome. */
  note?: string | null;
  notices?: FixNotice[];
}

export interface SeparationState {
  status: 'running' | 'cancelled' | 'failed';
  /** ms since epoch — Demucs reports no progress, so elapsed time is the story. */
  startedAt: number;
  error?: string | null;
}

export interface AnalysisState {
  status: 'running' | 'done' | 'cancelled' | 'failed';
  /** One row per console row: its checks run so far, of how many. */
  rows: TaskRow[];
  error?: string | null;
}

/** The console fetching rows' fixed audio so it can play them. */
export interface PlaybackLoad {
  /** The rows still on their way. */
  rows: string[];
  done: number;
  total: number;
  /**
   * Fetching what a render just finished, rather than rendering anything new.
   * That is the render's own last step, so it is shown as part of it: the
   * producer asked for one render, and should see one task.
   */
  afterRender: boolean;
}

export interface TaskInput {
  separation: SeparationState | null;
  analysis: AnalysisState | null;
  render: AcceptJob;
  playback: PlaybackLoad | null;
  now: number;
}

export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes}m ${String(seconds % 60).padStart(2, '0')}s` : `${seconds}s`;
}

/** `reduce_noise` → `reduce noise`: tool names are what the progress knows. */
export function toolLabel(tool: string): string {
  return tool.replace(/_/g, ' ');
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

function separationTask(state: SeparationState, now: number): Task {
  if (state.status === 'cancelled') {
    return {
      id: 'separate',
      title: 'Separation cancelled',
      detail: 'This version keeps the stems it had.',
      // Demucs is one uninterruptible call on the server (PROD-19 says so).
      note: 'The GPU finishes its current pass in the background, then throws the result away.',
      state: 'cancelled',
    };
  }
  if (state.status === 'failed') {
    return {
      id: 'separate',
      title: 'Separation failed',
      detail: state.error || 'Something went wrong separating the stems.',
      state: 'failed',
    };
  }
  return {
    id: 'separate',
    title: 'Separating into stems',
    detail: `${formatElapsed(now - state.startedAt)} so far · usually a minute or two`,
    state: 'running',
    cancelLabel: 'Cancel',
  };
}

function analysisTask(state: AnalysisState): Task {
  const done = state.rows.reduce((sum, row) => sum + row.done, 0);
  const total = state.rows.reduce((sum, row) => sum + row.total, 0);
  const measured = state.rows.filter((row) => row.total > 0 && row.done >= row.total).length;
  const parts = state.rows.length;

  if (state.status === 'cancelled') {
    return {
      id: 'analyze',
      title: 'Analysis cancelled',
      detail:
        measured > 0
          ? `Fixes from the ${plural(measured, 'part', 'parts')} already measured are kept.`
          : 'Nothing was measured yet.',
      note: 'Analyze the rest one part at a time from the console, or start again.',
      state: 'cancelled',
      done,
      total,
      rows: state.rows,
    };
  }
  if (state.status === 'failed') {
    return {
      id: 'analyze',
      title: 'Analysis failed',
      detail: state.error || 'Something went wrong measuring the stems.',
      state: 'failed',
      rows: state.rows,
    };
  }
  if (state.status === 'done') {
    return {
      id: 'analyze',
      title: 'Analysis done',
      detail: `${plural(parts, 'part', 'parts')} measured · ${plural(total, 'check', 'checks')}`,
      state: 'done',
      done: total,
      total,
    };
  }
  const current = state.rows.find((row) => row.done > 0 && row.done < row.total);
  return {
    id: 'analyze',
    title: 'Measuring the stems',
    detail: `${measured} of ${plural(parts, 'part', 'parts')} measured${
      current ? ` · ${current.label} ${current.done}/${current.total}` : ''
    }`,
    state: 'running',
    done,
    total,
    rows: state.rows,
    cancelLabel: 'Cancel',
  };
}

function renderTask(job: AcceptJob, playback: PlaybackLoad | null): Task | null {
  const saving = job.preview === false;
  const title = saving ? 'Saving new version' : 'Rendering fixes';

  if (job.status === 'idle') return null;

  // The render is done on the server; the console is still fetching it. One
  // task, still running, until the audio is actually playable.
  if (job.status === 'complete' && !saving && playback?.afterRender) {
    return {
      id: 'render',
      title,
      detail: `Loading playback · ${playback.done} of ${plural(playback.total, 'stem', 'stems')}`,
      state: 'running',
      done: playback.done,
      total: playback.total,
      note: 'Until it has loaded you hear the original audio.',
      cancelLabel: 'Play without',
    };
  }

  if (job.status === 'failed') {
    return {
      id: 'render',
      title: saving ? 'Save failed' : 'Render failed',
      detail: job.error || 'Something went wrong rendering this mix.',
      state: 'failed',
    };
  }

  if (job.status === 'cancelled') {
    return {
      id: 'render',
      title: saving ? 'Save cancelled' : 'Render cancelled',
      detail: 'No version was made. Stems whose fixes finished are kept for next time.',
      state: 'cancelled',
    };
  }

  if (job.status === 'complete') {
    return {
      id: 'render',
      title: saving ? 'Saved as a new version' : 'Fixes rendered',
      detail: saving
        ? 'Select it in the versions list to hear it or make it the default.'
        : job.reused
          ? 'Already rendered — nothing had to be redone.'
          : 'Ready to play in the console and to save.',
      state: 'done',
      notices: job.notices ?? [],
    };
  }

  const progress = job.progress ?? {};
  const total = progress.total ?? job.fix_count ?? 0;
  const done = Math.min(progress.done ?? 0, total);
  const stemsLeft = Math.max(0, (progress.stems_total ?? 0) - (progress.stems_done ?? 0));

  let detail: string;
  switch (progress.stage) {
    case 'remix':
      detail = 'Mixing the fixed stems back together';
      break;
    case 'master':
      detail = progress.tool
        ? `Full mix: ${toolLabel(progress.tool)}`
        : 'Applying the full-mix fixes';
      break;
    case 'playback':
      detail = `Preparing playback · ${progress.playback_done ?? 0} of ${plural(
        progress.playback_total ?? 0,
        'stem',
        'stems'
      )}`;
      break;
    case 'saving':
      detail = 'Writing the new version';
      break;
    case 'stems':
      detail = `${progress.stem ?? 'Stem'}: ${toolLabel(progress.tool ?? '')} · ${plural(
        stemsLeft,
        'stem',
        'stems'
      )} left`;
      break;
    default:
      detail = `Starting on ${plural(total, 'fix', 'fixes')}`;
  }

  return {
    id: 'render',
    title,
    detail,
    state: 'running',
    done,
    total,
    // The version row is being written: stopping now could leave half a save.
    cancelLabel: progress.stage === 'saving' ? null : saving ? 'Cancel save' : 'Cancel',
    note:
      saving && progress.stage !== 'saving'
        ? 'Saves the moment the render finishes.'
        : null,
  };
}

function playbackTask(playback: PlaybackLoad | null): Task | null {
  if (!playback || playback.afterRender || playback.rows.length === 0) return null;
  return {
    id: 'playback',
    title: 'Rendering fixes to play',
    detail: `${playback.done} of ${plural(playback.total, 'stem', 'stems')} · ${playback.rows.join(', ')}`,
    note: 'Until they are ready you hear the original audio on these.',
    state: 'running',
    done: playback.done,
    total: playback.total,
    cancelLabel: 'Play without',
  };
}

/** Every task worth showing, in the order the work happens. */
export function buildTasks(input: TaskInput): Task[] {
  return [
    input.separation ? separationTask(input.separation, input.now) : null,
    input.analysis ? analysisTask(input.analysis) : null,
    renderTask(input.render, input.playback),
    playbackTask(input.playback),
  ].filter((task): task is Task => task !== null);
}

/** The collapsed panel's one line: the first running task, counted. */
export function summarizeTasks(tasks: Task[]): string {
  const running = tasks.find((task) => task.state === 'running');
  if (!running) {
    const last = tasks[tasks.length - 1];
    return last ? last.title : '';
  }
  if (running.total) return `${running.title} · ${running.done ?? 0}/${running.total}`;
  return running.title;
}
