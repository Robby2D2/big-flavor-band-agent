'use client';

import { useMemo } from 'react';
import {
  LyricLine,
  findActiveWord,
  findDisplayLine,
} from '@/lib/lyricTimings';

export interface ActiveLyric {
  /** Line to highlight, or -1 before the first line. Holds through gaps. */
  lineIndex: number;
  /** Word within that line, or -1 when the line has no word timings / is in a gap. */
  wordIndex: number;
}

/**
 * Resolve which lyric line/word is current at `currentTime`.
 *
 * `useMemo` on the two indices — not the objects — is what keeps this cheap
 * under a 60fps time source: the caller re-renders every frame, but the memo's
 * inputs only change when the *time* changes, and consumers comparing indices
 * see the same primitive values on ~59 of every 60 frames.
 */
export function useActiveLyric(lines: LyricLine[], currentTime: number): ActiveLyric {
  return useMemo(() => {
    if (!lines.length) return { lineIndex: -1, wordIndex: -1 };
    const lineIndex = findDisplayLine(lines, currentTime);
    const wordIndex =
      lineIndex === -1 ? -1 : findActiveWord(lines[lineIndex], currentTime);
    return { lineIndex, wordIndex };
  }, [lines, currentTime]);
}
