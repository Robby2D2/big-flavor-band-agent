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

/** The processing steps a version had applied, as a sentence fragment. */
export function formatSteps(steps: { step: string }[] | null | undefined): string {
  return steps && steps.length > 0 ? steps.map((s) => s.step).join(', ') : '—';
}
