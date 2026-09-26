/**
 * The four things the radio page can say is on the air (issue #101).
 *
 * The page used to show whatever the backend's own clock had counted up to, so
 * these cases are the display side of "never present a song we cannot vouch for":
 * a queued song, fallback catalog music named rather than hidden, an unreachable
 * stream reported as unknown, and a track with no catalog duration still showing
 * its position (CAT-02).
 */
import { describe, it, expect } from 'vitest';

import { describeNowPlaying } from '@/lib/nowPlaying';

const song = { id: 12, title: 'So Tired', duration: 400 };

describe('describeNowPlaying', () => {
  it('names a queued song with its progress', () => {
    const result = describeNowPlaying({
      current_song: song,
      stream_known: true,
      current_song_source: 'queue',
      position: 100,
    });

    expect(result.kind).toBe('queued');
    expect(result.song).toEqual(song);
    expect(result.duration).toBe(400);
    expect(result.progress).toBeCloseTo(0.25);
  });

  it('names fallback music and distinguishes it from a queued song', () => {
    const result = describeNowPlaying({
      current_song: song,
      stream_known: true,
      current_song_source: 'fallback',
      position: 10,
    });

    expect(result.kind).toBe('fallback');
    expect(result.song?.title).toBe('So Tired');
  });

  it('reports unknown when the stream could not be asked, and names no song', () => {
    const result = describeNowPlaying({
      current_song: song,
      stream_known: false,
      current_song_source: 'queue',
      position: 100,
    });

    expect(result.kind).toBe('unknown');
    expect(result.song).toBeNull();
    expect(result.progress).toBeNull();
  });

  it('fails closed: a payload that never says the stream was reached is unknown', () => {
    expect(describeNowPlaying({ current_song: song }).kind).toBe('unknown');
    expect(describeNowPlaying(null).kind).toBe('unknown');
  });

  it('is silent when the stream is reachable but nothing nameable is playing', () => {
    const result = describeNowPlaying({ current_song: null, stream_known: true, position: 3 });

    expect(result.kind).toBe('silent');
    expect(result.song).toBeNull();
  });

  it('falls back to the length the stream reports when the catalog has no duration', () => {
    const result = describeNowPlaying({
      current_song: { id: 7, title: 'No duration', duration: null },
      stream_known: true,
      current_song_source: 'queue',
      stream_duration: 200,
      position: 50,
    });

    expect(result.duration).toBe(200);
    expect(result.progress).toBeCloseTo(0.25);
  });

  it('shows a position but no progress bar when no length is known at all', () => {
    const result = describeNowPlaying({
      current_song: { id: 7, title: 'No duration' },
      stream_known: true,
      current_song_source: 'queue',
      stream_duration: null,
      position: 50,
    });

    expect(result.kind).toBe('queued');
    expect(result.position).toBe(50);
    expect(result.duration).toBeNull();
    expect(result.progress).toBeNull();
  });

  it('clamps progress so a stream running past a stale catalog duration cannot overflow', () => {
    const result = describeNowPlaying({
      current_song: { id: 7, title: 'Longer than the catalog thinks', duration: 100 },
      stream_known: true,
      current_song_source: 'queue',
      position: 250,
    });

    expect(result.progress).toBe(1);
  });
});
