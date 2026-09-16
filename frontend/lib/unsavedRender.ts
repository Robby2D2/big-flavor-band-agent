/**
 * The rendered-but-unsaved mix that Start analysis leaves behind.
 *
 * Analysis renders the queue it detected, so by the time the findings are on
 * screen there is a finished mix on disk that belongs to no version yet. It
 * gets a row in the versions list — selectable, so the producer can flip
 * between it and the original and hear the difference before deciding to keep
 * it. Saving it is still "Accept all & save version"; this row is for listening.
 */
import type { AcceptJob } from '@/hooks/useAcceptJob';

/** Sentinel id for the pseudo-row. Never collides: real version ids are > 0. */
export const UNSAVED_VERSION_ID = -1;

export interface UnsavedRender {
  candidatePath: string;
  fixCount: number;
  renderedAt: number | null;
}

/** The unsaved mix a finished render left behind, or null if there isn't one. */
export function unsavedRenderFrom(job: AcceptJob): UnsavedRender | null {
  // Only a preview render leaves an unsaved mix. A save became a real version,
  // which is already in the list on its own merits.
  if (job.status !== 'complete' || !job.preview) return null;

  const path = (job as { candidate_path?: string }).candidate_path;
  if (!path) return null;

  return {
    candidatePath: path,
    fixCount: job.fix_count ?? 0,
    renderedAt: (job as { finished_at?: number }).finished_at ?? null,
  };
}

/** Where to stream an unsaved render from — it has no version id to play by. */
export function unsavedRenderAudioUrl(candidatePath: string): string {
  return `/api/produce/clean/preview?path=${encodeURIComponent(candidatePath)}`;
}

/** How the row labels itself in the versions table. */
export function unsavedRenderLabel(render: UnsavedRender): string {
  const fixes = render.fixCount === 1 ? '1 fix' : `${render.fixCount} fixes`;
  return `${fixes} applied · not saved yet`;
}
