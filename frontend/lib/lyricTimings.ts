// Shared types + pure lookup logic for timed lyrics (follow-along highlighting).
//
// Deliberately framework-free: the same `findActiveLine` runs against every
// playback surface (the <audio> element player, the produce page's AudioContext
// stem playback, the radio's polled position) and is unit-tested directly.

export interface LyricWord {
  start: number;
  end: number;
  text: string;
  probability?: number;
}

export interface LyricLine {
  start: number;
  end: number;
  text: string;
  confidence?: number;
  words?: LyricWord[];
}

export interface LyricTimings {
  format_version: number;
  source: string | null;
  model: string | null;
  audio_source: string | null;
  /** 'current' — safe to highlight. 'stale' — text was edited after extraction. */
  status: string | null;
  lines: LyricLine[];
}

export interface TimedLyricsResponse {
  song_id: number;
  lyrics: string;
  timings: LyricTimings | null;
}

/** Timings are only safe to highlight when they still match the stored text. */
export function isFollowable(timings: LyricTimings | null | undefined): boolean {
  return Boolean(timings && timings.status !== 'stale' && timings.lines.length > 0);
}

/**
 * Index of the line active at `time`, or -1 when none is (before the first
 * line, or in an instrumental gap between lines).
 *
 * Lines are sorted and non-overlapping as Whisper emits them, so this is a
 * binary search: O(log n) makes an arbitrary seek as cheap as a sequential
 * step, which is why the caller doesn't need to maintain a cursor.
 */
export function findActiveLine(lines: LyricLine[], time: number): number {
  let lo = 0;
  let hi = lines.length - 1;
  let found = -1;

  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const line = lines[mid];
    if (time < line.start) {
      hi = mid - 1;
    } else if (time >= line.end) {
      lo = mid + 1;
    } else {
      found = mid;
      break;
    }
  }

  return found;
}

/**
 * Index of the active word within a line, or -1 when none is.
 *
 * Words are searched linearly: a line holds a handful of them, and the extra
 * branching of a binary search costs more than it saves at that size.
 */
export function findActiveWord(line: LyricLine | undefined, time: number): number {
  if (!line?.words?.length) return -1;
  for (let i = 0; i < line.words.length; i++) {
    const word = line.words[i];
    if (time >= word.start && time < word.end) return i;
  }
  return -1;
}

/**
 * Index of the line to *display* as current at `time`.
 *
 * Differs from `findActiveLine` in gaps: during an instrumental break the last
 * line that was sung stays highlighted rather than the view snapping back to
 * nothing, which reads as the lyrics having lost their place. Returns -1 only
 * before the first line starts.
 */
export function findDisplayLine(lines: LyricLine[], time: number): number {
  const active = findActiveLine(lines, time);
  if (active !== -1) return active;

  // In a gap: fall back to the last line that has already ended.
  let lo = 0;
  let hi = lines.length - 1;
  let previous = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (lines[mid].end <= time) {
      previous = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return previous;
}
