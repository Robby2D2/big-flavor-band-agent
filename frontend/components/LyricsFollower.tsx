'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { LyricLine } from '@/lib/lyricTimings';
import { useActiveLyric } from '@/hooks/useActiveLyric';

// ---------------------------------------------------------------------------
// Follow-along lyrics: highlights the line (and word, where word timings exist)
// being sung at `currentTime`.
//
// Deliberately presentational and time-source agnostic — it takes a number of
// seconds, not a player. That's what lets the same component serve the <audio>
// player, the produce page's AudioContext stem playback, and the radio's polled
// position without knowing anything about them.
// ---------------------------------------------------------------------------

// How long to leave autoscroll off after the user scrolls by hand. Long enough
// to read a verse without the view yanking back, short enough that passive
// listening resumes following on its own.
const MANUAL_SCROLL_PAUSE_MS = 4000;

interface LyricsFollowerProps {
  lines: LyricLine[];
  currentTime: number;
  /** Seek the player to a line's start. Omit to make lines non-interactive. */
  onSeek?: (time: number) => void;
  className?: string;
}

export default function LyricsFollower({
  lines,
  currentTime,
  onSeek,
  className = '',
}: LyricsFollowerProps) {
  const { lineIndex, wordIndex } = useActiveLyric(lines, currentTime);
  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLParagraphElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Set while *we* are scrolling, so our own smooth scroll doesn't trip the
  // manual-scroll detector and immediately disable autoscroll.
  const programmaticScrollRef = useRef(false);

  const pauseAutoScroll = useCallback(() => {
    setAutoScroll(false);
    if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current);
    resumeTimerRef.current = setTimeout(
      () => setAutoScroll(true),
      MANUAL_SCROLL_PAUSE_MS
    );
  }, []);

  const handleScroll = useCallback(() => {
    if (programmaticScrollRef.current) {
      programmaticScrollRef.current = false;
      return;
    }
    pauseAutoScroll();
  }, [pauseAutoScroll]);

  useEffect(
    () => () => {
      if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current);
    },
    []
  );

  // Keep the active line centered. Depends on lineIndex (not currentTime), so it
  // runs once per line change rather than once per frame.
  useEffect(() => {
    if (!autoScroll || lineIndex === -1) return;
    const node = activeRef.current;
    if (!node) return;

    const reduceMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

    programmaticScrollRef.current = true;
    node.scrollIntoView({
      block: 'center',
      behavior: reduceMotion ? 'auto' : 'smooth',
    });
  }, [lineIndex, autoScroll]);

  const jumpToCurrent = () => {
    if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current);
    setAutoScroll(true);
  };

  if (!lines.length) return null;

  return (
    <div className={`relative ${className}`}>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        data-testid="lyrics-scroll"
        className="max-h-64 overflow-y-auto px-2 py-3 space-y-2"
      >
        {lines.map((line, i) => {
          const isActive = i === lineIndex;
          const hasWords = Boolean(line.words?.length);

          return (
            <p
              key={`${line.start}-${i}`}
              ref={isActive ? activeRef : undefined}
              data-testid={`lyric-line-${i}`}
              data-active={isActive || undefined}
              onClick={onSeek ? () => onSeek(line.start) : undefined}
              className={[
                'text-base leading-relaxed transition-colors duration-200',
                onSeek ? 'cursor-pointer' : '',
                // Inactive lines stay legible rather than near-invisible — the
                // point is to read ahead and behind, not just the current line.
                isActive ? 'text-text font-semibold' : 'text-text/50',
              ].join(' ')}
            >
              {isActive && hasWords
                ? line.words!.map((word, w) => (
                    <span
                      key={`${word.start}-${w}`}
                      data-testid={w === wordIndex ? 'lyric-word-active' : undefined}
                      data-active={w === wordIndex || undefined}
                      className={
                        w === wordIndex ? 'text-signal' : 'text-text'
                      }
                    >
                      {word.text}{' '}
                    </span>
                  ))
                : line.text}
            </p>
          );
        })}
      </div>

      {!autoScroll && lineIndex !== -1 && (
        <button
          onClick={jumpToCurrent}
          className="absolute bottom-2 right-2 text-xs px-3 py-1 rounded-full bg-signal text-canvas font-medium shadow-lg"
        >
          Jump to current
        </button>
      )}
    </div>
  );
}
