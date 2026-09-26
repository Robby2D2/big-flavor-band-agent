/**
 * Which radio queue controls a signed-in user is offered, and what to tell them when
 * an action is refused.
 *
 * Deciding this in the browser is a **courtesy**, not a gate: it keeps a listener from
 * being shown a button that would only fail (ACCT-08), while the backend authorizes
 * the action itself against the queue's own attribution (ACCT-04). Pure logic, so it
 * lives here and is unit-tested rather than tangled into the page — same split as
 * `lib/nowPlaying.ts`.
 */

/** The only part of a queue entry that decides whether Remove is offered. */
export interface QueueEntryOwnership {
  /**
   * Set by the backend per reader: whether the user who fetched the state is the one
   * who queued this song. Absent or false covers songs somebody else queued and songs
   * with no recorded adder at all — queued before attribution existed, topped up
   * automatically, or asked for through the DJ (RAD-13).
   */
  added_by_me?: boolean;
}

/** Whether a role may change what is on the air: skip, play/pause, remove anything. */
export function isEditorRole(role: string | null | undefined): boolean {
  return role === 'editor' || role === 'admin';
}

/**
 * Whether to offer Remove on a queued song.
 *
 * An editor or admin may remove any queued song; anyone else only one they added
 * themselves (ACCT-05, ACCT-15).
 */
export function canRemoveQueueEntry(
  entry: QueueEntryOwnership | null | undefined,
  role: string | null | undefined
): boolean {
  if (isEditorRole(role)) return true;
  return entry?.added_by_me === true;
}

/**
 * What to show the user when a queue action did not happen.
 *
 * The backend's own wording wins where there is one — a refused removal explains
 * itself far better than a status code can — and every other case still gets a
 * sentence rather than a silent failure (RAD-09, PLAT-07).
 */
export function queueActionError(
  status: number,
  body: { error?: unknown } | null | undefined,
  fallback: string
): string {
  const reported = body?.error;
  if (typeof reported === 'string' && reported.trim() !== '') {
    return reported;
  }

  if (status === 401) return 'Your session has expired — please sign in again.';
  if (status === 403) return "You don't have permission to do that.";

  return fallback;
}
