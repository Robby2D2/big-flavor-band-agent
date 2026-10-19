/**
 * Rendered "takes" of a console row: the row's audio run through one particular
 * set of enabled fixes.
 *
 * Switching a fix ON/OFF is an A/B comparison, and it only feels instant if
 * the take for the other state is already decoded. So the page keeps several
 * takes per row, keyed by the chain that produced them, and renders the takes
 * one toggle away from what is playing ahead of time. Pure logic, kept out of
 * the component so it can be unit-tested.
 */

/** The part of a fix card that decides what a render sounds like. */
export interface ChainFix {
  id: string;
  tool: string;
  currentParams: Record<string, any>;
  enabled: boolean;
}

export interface ChainStep {
  tool: string;
  params: Record<string, any>;
}

/**
 * Identifies a row's chain: its enabled fixes, in order, with their params.
 * Empty when nothing is enabled, which means the raw audio is the take.
 */
export function chainSignature(fixes: ChainFix[]): string {
  const enabled = fixes
    .filter((f) => f.enabled)
    .map((f) => ({ tool: f.tool, params: f.currentParams }));
  return enabled.length ? JSON.stringify(enabled) : '';
}

/**
 * Every chain one ON/OFF away from the row's current one, with the signature
 * the row will have after that toggle.
 *
 * A fix that can't run yet (a required param is blank) is skipped: turning it
 * on renders nothing new. A neighbour that runs no fix at all is left out too,
 * since the raw audio is always loaded already.
 */
export function neighbourChains<F extends ChainFix>(
  fixes: F[],
  isIncomplete: (fix: F) => boolean
): { signature: string; chain: ChainStep[] }[] {
  const neighbours: { signature: string; chain: ChainStep[] }[] = [];
  for (const flipped of fixes) {
    if (isIncomplete(flipped)) continue;
    const next = fixes.map((f) => (f.id === flipped.id ? { ...f, enabled: !f.enabled } : f));
    const chain = next
      .filter((f) => f.enabled && !isIncomplete(f))
      .map((f) => ({ tool: f.tool, params: f.currentParams }));
    if (!chain.length) continue;
    neighbours.push({ signature: chainSignature(next), chain });
  }
  return neighbours;
}

export function takeKey(rowId: number, signature: string): string {
  return `${rowId}|${signature}`;
}

/**
 * Add a take and drop the oldest ones past `max`, never one in `keep`.
 *
 * A decoded stem is tens of MB, so the cache has to stay small; the takes
 * that are playing right now are the ones that must survive.
 */
export function addTake<T>(
  takes: Map<string, T>,
  key: string,
  take: T,
  keep: Set<string>,
  max: number
): Map<string, T> {
  const next = new Map(takes);
  // Re-inserting moves it to the newest end, so a take just heard is kept longest.
  next.delete(key);
  next.set(key, take);
  for (const k of Array.from(next.keys())) {
    if (next.size <= max) break;
    if (k !== key && !keep.has(k)) next.delete(k);
  }
  return next;
}
