import { describe, expect, it } from 'vitest';
import {
  LyricLine,
  findActiveLine,
  findActiveWord,
  findDisplayLine,
  isFollowable,
} from '@/lib/lyricTimings';

// Three lines with a deliberate instrumental gap between line 1 (ends 8) and
// line 2 (starts 12) — gaps are where the display/active distinction matters.
const lines: LyricLine[] = [
  {
    start: 2,
    end: 5,
    text: 'Headed down south',
    words: [
      { start: 2, end: 2.5, text: 'Headed' },
      { start: 2.5, end: 3.2, text: 'down' },
      { start: 3.2, end: 5, text: 'south' },
    ],
  },
  { start: 5, end: 8, text: 'to the land of the pines' },
  { start: 12, end: 16, text: 'And I am thumbing my way' },
];

describe('findActiveLine', () => {
  it('returns -1 before the first line starts', () => {
    expect(findActiveLine(lines, 0)).toBe(-1);
    expect(findActiveLine(lines, 1.99)).toBe(-1);
  });

  it('finds the line covering the time', () => {
    expect(findActiveLine(lines, 2)).toBe(0);
    expect(findActiveLine(lines, 4.9)).toBe(0);
    expect(findActiveLine(lines, 6)).toBe(1);
    expect(findActiveLine(lines, 15.9)).toBe(2);
  });

  it('treats a line as active at its start and inactive at its end', () => {
    // Adjacent lines share a boundary (line 0 ends at 5, line 1 starts at 5);
    // a half-open interval keeps exactly one of them active.
    expect(findActiveLine(lines, 5)).toBe(1);
  });

  it('returns -1 inside an instrumental gap', () => {
    expect(findActiveLine(lines, 10)).toBe(-1);
  });

  it('returns -1 after the last line ends', () => {
    expect(findActiveLine(lines, 999)).toBe(-1);
  });

  it('handles an empty line list', () => {
    expect(findActiveLine([], 5)).toBe(-1);
  });
});

describe('findDisplayLine', () => {
  it('matches findActiveLine while a line is being sung', () => {
    expect(findDisplayLine(lines, 6)).toBe(1);
  });

  it('holds the previous line through an instrumental gap', () => {
    expect(findDisplayLine(lines, 10)).toBe(1);
  });

  it('holds the final line after the song stops singing', () => {
    expect(findDisplayLine(lines, 999)).toBe(2);
  });

  it('still returns -1 before the first line', () => {
    expect(findDisplayLine(lines, 0)).toBe(-1);
  });
});

describe('findActiveWord', () => {
  it('finds the word covering the time', () => {
    expect(findActiveWord(lines[0], 2.1)).toBe(0);
    expect(findActiveWord(lines[0], 2.6)).toBe(1);
    expect(findActiveWord(lines[0], 4)).toBe(2);
  });

  it('returns -1 for a line without word timings', () => {
    expect(findActiveWord(lines[1], 6)).toBe(-1);
  });

  it('returns -1 when no word covers the time', () => {
    expect(findActiveWord(lines[0], 1)).toBe(-1);
  });

  it('returns -1 for a missing line', () => {
    expect(findActiveWord(undefined, 3)).toBe(-1);
  });
});

describe('isFollowable', () => {
  const base = {
    format_version: 1,
    source: 'whisper',
    model: 'large-v3',
    audio_source: 'vocals_stem',
  };

  it('is followable when current with lines', () => {
    expect(isFollowable({ ...base, status: 'current', lines })).toBe(true);
  });

  it('is not followable when the text was edited after extraction', () => {
    expect(isFollowable({ ...base, status: 'stale', lines })).toBe(false);
  });

  it('is not followable with no timings at all', () => {
    expect(isFollowable(null)).toBe(false);
    expect(isFollowable({ ...base, status: 'current', lines: [] })).toBe(false);
  });
});
