'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Follows a song's background "accept fixes" render.
 *
 * Rendering a full review queue takes minutes, so it no longer happens inside a
 * request — the page starts it and watches it here. Polling begins on mount, so
 * a reload in the middle of a render picks it straight back up instead of
 * looking idle while the server is still working.
 */

export type AcceptJobStatus = 'idle' | 'running' | 'complete' | 'failed';

/**
 * A fix that succeeded but did less than its card promised.
 *
 * Today only `correct_pitch` raises one, when the source turns out not to be a
 * single line and it shifts the whole file instead of correcting note by note.
 * Accepting a fix and being handed back unchanged audio with nothing said is
 * the outcome this exists to prevent (issue #91).
 */
export interface FixNotice {
  /** The stem name the fix ran on, or `master` for the full-mix bucket. */
  scope: string;
  tool: string;
  /** The tool's own words for what it did instead. */
  reason: string;
}

export interface AcceptJob {
  status: AcceptJobStatus;
  /** A preview render makes no version; a save does. */
  preview?: boolean;
  fix_count?: number;
  started_at?: number;
  version?: { version_id: number; is_published: boolean } | null;
  error?: string | null;
  /** The render was already on disk — nothing was re-rendered. */
  reused?: boolean;
  /** Fixes that ran but did less than their card said. */
  notices?: FixNotice[];
}

const POLL_MS = 2500;

/** What the versions list should say about this render, if anything. */
export function describeAcceptJob(job: AcceptJob): {
  label: string;
  detail: string;
  tone: 'progress' | 'error';
} | null {
  if (job.status === 'running') {
    const fixes = job.fix_count === 1 ? '1 fix' : `${job.fix_count ?? 0} fixes`;
    return {
      label: job.preview ? 'Rendering preview…' : 'Saving new version…',
      detail: `applying ${fixes} · this can take a few minutes`,
      tone: 'progress',
    };
  }

  if (job.status === 'failed') {
    return {
      label: 'Render failed',
      detail: job.error || 'Something went wrong rendering this mix.',
      tone: 'error',
    };
  }

  return null;
}

export function useAcceptJob(
  songId: number,
  /** Called with the id of the version a finished save produced. */
  onVersionSaved: (versionId: number | null) => void
) {
  const [job, setJob] = useState<AcceptJob>({ status: 'idle' });
  // Bumped to re-run the poll loop after starting a render, so there is only
  // ever one implementation of the polling itself.
  const [nonce, setNonce] = useState(0);

  // Keep the callback current without restarting the loop on every render.
  const savedCallback = useRef(onVersionSaved);
  useEffect(() => {
    savedCallback.current = onVersionSaved;
  }, [onVersionSaved]);

  const dismiss = useCallback(async () => {
    setJob({ status: 'idle' });
    try {
      await fetch(`/api/produce/songs/${songId}/accept-fixes/dismiss`, { method: 'POST' });
    } catch {
      // Dismissing is bookkeeping; the row is already gone from the UI.
    }
  }, [songId]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    let wasRunning = false;

    const tick = async () => {
      let current: AcceptJob = { status: 'idle' };
      try {
        const response = await fetch(`/api/produce/songs/${songId}/accept-fixes/status`);
        if (response.ok) current = (await response.json()) as AcceptJob;
      } catch {
        // A dropped poll is not a failed render; try again on the next tick.
        if (!cancelled && wasRunning) timer = setTimeout(tick, POLL_MS);
        return;
      }
      if (cancelled) return;

      setJob(current);

      // A finished save is the moment the new version exists: reload the list,
      // then clear the job so the progress row goes away. A cache hit lands
      // here on the very first poll, having never been "running".
      if (current.status === 'complete' && !current.preview) {
        savedCallback.current(current.version?.version_id ?? null);
        void dismiss();
        return;
      }

      if (current.status === 'running') {
        wasRunning = true;
        timer = setTimeout(tick, POLL_MS);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [songId, nonce, dismiss]);

  /** Called right after starting a render, so polling picks it up at once. */
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  return { job, refresh, dismiss };
}
