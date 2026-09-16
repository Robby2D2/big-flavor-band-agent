/**
 * Formatting shared by the version list and the version details panel.
 *
 * Both render the same size/duration/date facts about a song version, so the
 * rules for "—" and for rounding live here rather than in each component.
 */

/** Human-readable byte size, or "—" when the size is unknown. */
export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return '—';
  if (bytes < 1024) return `${bytes} B`;

  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(1)} ${units[unit]}`;
}

/** m:ss, or "—" when the duration is unknown. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '—';

  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  // Rounding 59.6s up must roll over into the next minute, not read "3:60".
  if (secs === 60) {
    return `${minutes + 1}:00`;
  }
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

/** Local date+time a version was produced, or "—". */
export function formatProducedAt(isoDate: string | null | undefined): string {
  if (!isoDate) return '—';
  const parsed = new Date(isoDate);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleString();
}

/** One entry in a version's `steps_applied`, in either shape it is written in. */
export interface AppliedStep {
  /** Whole-mix fix: {"step": "normalize_audio", "scope": "master"}. */
  step?: string;
  /** Per-stem fixes: {"stem": 44, "tools": ["apply_eq", "correct_beats"]}. */
  stem?: number;
  tools?: string[];
}

/**
 * The processing a version had applied, as a sentence fragment.
 *
 * `steps_applied` holds two shapes in the same array — accept-fixes writes one
 * entry per stem carrying a list of tools, plus one per whole-mix fix carrying a
 * single tool name. Reading only `.step` rendered "undefined" for every per-stem
 * entry. Tools are de-duplicated: the same fix applied across six stems is one
 * thing the listener did, not six.
 */
export function formatSteps(steps: AppliedStep[] | null | undefined): string {
  if (!steps || steps.length === 0) return '—';

  const tools: string[] = [];
  for (const entry of steps) {
    if (!entry) continue;
    const names = entry.tools ?? (entry.step ? [entry.step] : []);
    for (const name of names) {
      if (typeof name === 'string' && name && !tools.includes(name)) {
        tools.push(name);
      }
    }
  }

  return tools.length > 0 ? tools.join(', ') : '—';
}
