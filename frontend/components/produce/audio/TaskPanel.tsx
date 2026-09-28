'use client';

import { useState } from 'react';

import type { Task, TaskId } from '@/lib/processingTasks';
import { summarizeTasks } from '@/lib/processingTasks';

import FixNoticePanel from './FixNoticePanel';
import Spinner from './Spinner';

interface TaskPanelProps {
  tasks: Task[];
  onCancel: (id: TaskId) => void;
  /** Offered on a failed or cancelled task when there is a way to run it again. */
  onRetry?: (id: TaskId) => void;
  /** Clear the finished tasks. Running ones stay. */
  onDismiss: () => void;
}

/** How many of a task's per-part rows to list before summarising the rest. */
const MAX_ROWS = 8;

function StateIcon({ task }: { task: Task }) {
  if (task.state === 'running') return <Spinner className="w-3.5 h-3.5 text-signal" />;
  if (task.state === 'done') return <span className="text-confirm text-sm leading-none">✓</span>;
  if (task.state === 'failed') return <span className="text-red-400 text-sm leading-none">!</span>;
  return <span className="text-text/40 text-sm leading-none">–</span>;
}

function TaskItem({
  task,
  onCancel,
  onRetry,
}: {
  task: Task;
  onCancel: (id: TaskId) => void;
  onRetry?: (id: TaskId) => void;
}) {
  const pct = task.total ? Math.round(((task.done ?? 0) / task.total) * 100) : null;
  const canRetry = onRetry && (task.state === 'failed' || task.state === 'cancelled');

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex w-4 justify-center">
          <StateIcon task={task} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold text-text">{task.title}</span>
            {pct !== null && task.state === 'running' && (
              <span className="font-mono text-[10.5px] tabular-nums text-text/50">
                {task.done}/{task.total}
              </span>
            )}
          </div>
          <p className="mt-0.5 break-words text-xs text-text/60">{task.detail}</p>

          {pct !== null && task.state === 'running' && (
            <div className="mt-2 h-1 overflow-hidden rounded bg-well">
              <div
                className="h-full bg-signal transition-[width] duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}

          {task.rows && task.rows.length > 0 && task.state === 'running' && (
            <ul className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5">
              {task.rows.slice(0, MAX_ROWS).map((row, i) => (
                <li
                  key={i}
                  className={`flex justify-between gap-2 font-mono text-[10.5px] ${
                    row.done >= row.total ? 'text-confirm/80' : 'text-text/45'
                  }`}
                >
                  <span className="truncate capitalize">{row.label}</span>
                  <span className="tabular-nums">
                    {row.done >= row.total ? '✓' : `${row.done}/${row.total}`}
                  </span>
                </li>
              ))}
              {task.rows.length > MAX_ROWS && (
                <li className="col-span-2 font-mono text-[10.5px] text-text/35">
                  +{task.rows.length - MAX_ROWS} more
                </li>
              )}
            </ul>
          )}

          {task.note && <p className="mt-1.5 text-[11px] text-text/40">{task.note}</p>}

          {task.notices && task.notices.length > 0 && (
            <div className="mt-2">
              <FixNoticePanel notices={task.notices} />
            </div>
          )}

          {(task.cancelLabel || canRetry) && (
            <div className="mt-2 flex gap-2">
              {task.state === 'running' && task.cancelLabel && (
                <button
                  type="button"
                  onClick={() => onCancel(task.id)}
                  className="rounded border border-white/14 px-2 py-1 text-xs text-text/70 hover:bg-white/5"
                >
                  {task.cancelLabel}
                </button>
              )}
              {canRetry && (
                <button
                  type="button"
                  onClick={() => onRetry(task.id)}
                  className="rounded border border-white/14 px-2 py-1 text-xs text-text/70 hover:bg-white/5"
                >
                  Retry
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

/**
 * Everything the produce page is working on, in one floating panel.
 *
 * Start analysis sets off up to four long jobs — separating, measuring,
 * rendering, and rendering again to play — that used to report through a note
 * under a button and a spinner on the play button. The panel counts each one,
 * says what it is doing right now, and offers to cancel it (PROD-19), since any
 * of them can run for minutes. Collapsed, it is one line that keeps counting.
 */
export default function TaskPanel({ tasks, onCancel, onRetry, onDismiss }: TaskPanelProps) {
  const [collapsed, setCollapsed] = useState(false);

  if (tasks.length === 0) return null;

  const running = tasks.filter((task) => task.state === 'running');
  const cancellable = running.filter((task) => task.cancelLabel);

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        aria-label="Show tasks"
        className="fixed bottom-4 right-4 z-40 flex max-w-[calc(100vw-2rem)] items-center gap-2 rounded-full border border-signal/30 bg-raised px-4 py-2.5 text-sm text-text shadow-lg"
      >
        {running.length > 0 ? (
          <Spinner className="w-3.5 h-3.5 text-signal" />
        ) : (
          <span className="text-confirm">✓</span>
        )}
        <span className="truncate">{summarizeTasks(tasks)}</span>
      </button>
    );
  }

  return (
    <section
      aria-label="Tasks"
      className="fixed inset-x-0 bottom-0 z-40 max-h-[60vh] overflow-y-auto rounded-t-xl border border-white/10 bg-raised p-4 shadow-2xl sm:inset-x-auto sm:bottom-4 sm:right-4 sm:w-[23rem] sm:rounded-xl"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="font-mono text-[10.5px] uppercase tracking-wider text-text/50">
          {running.length > 0 ? `Working · ${running.length}` : 'Tasks'}
        </h3>
        <div className="flex items-center gap-3">
          {cancellable.length > 1 && (
            <button
              type="button"
              onClick={() => cancellable.forEach((task) => onCancel(task.id))}
              className="text-xs text-red-300 hover:text-red-200"
            >
              Cancel all
            </button>
          )}
          {running.length === 0 && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-xs text-text/50 hover:text-text"
            >
              Clear
            </button>
          )}
          <button
            type="button"
            onClick={() => setCollapsed(true)}
            aria-label="Collapse tasks"
            className="text-xs text-text/50 hover:text-text"
          >
            ▾
          </button>
        </div>
      </div>

      <ul className="divide-y divide-white/8">
        {tasks.map((task) => (
          <TaskItem key={task.id} task={task} onCancel={onCancel} onRetry={onRetry} />
        ))}
      </ul>
    </section>
  );
}
