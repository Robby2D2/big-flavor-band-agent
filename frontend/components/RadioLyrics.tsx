'use client';

import { useEffect, useState } from 'react';
import LyricsFollower from './LyricsFollower';
import { LyricTimings, TimedLyricsResponse, isFollowable } from '@/lib/lyricTimings';

// ---------------------------------------------------------------------------
// Lyrics for the song on the air.
//
// The radio has no local player to read a clock from — only the position the
// page polls every few seconds. Between polls this runs the clock forward
// itself, so the follow-along highlight moves smoothly instead of jumping a few
// lines at a time. Lines are not seekable: the stream is shared (RAD-01), so no
// one listener can move it.
// ---------------------------------------------------------------------------

interface RadioLyricsProps {
  songId: number;
  /** Seconds into the song, as last reported by the radio state. */
  position: number;
  /** Whether the stream is advancing — the clock holds still while paused. */
  playing: boolean;
}

interface LoadedLyrics {
  songId: number;
  text: string;
  timings: LyricTimings | null;
}

export default function RadioLyrics({ songId, position, playing }: RadioLyricsProps) {
  // Kept with the song it was fetched for, so a song change shows a loading
  // state rather than the previous song's lyrics until the new fetch lands.
  const [loaded, setLoaded] = useState<LoadedLyrics | null>(null);
  const [failed, setFailed] = useState<number | null>(null);
  const lyrics = loaded?.songId === songId ? loaded : null;
  const [currentTime, setCurrentTime] = useState(position);

  useEffect(() => {
    let cancelled = false;

    fetch(`/api/songs/${songId}/lyrics/timed`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((data: TimedLyricsResponse) => {
        if (!cancelled) {
          setLoaded({ songId, text: data.lyrics ?? '', timings: data.timings ?? null });
        }
      })
      .catch(() => {
        if (!cancelled) setFailed(songId);
      });

    return () => {
      cancelled = true;
    };
  }, [songId]);

  const canFollow = isFollowable(lyrics?.timings);

  // Each poll re-anchors the clock; rAF carries it forward until the next one.
  useEffect(() => {
    setCurrentTime(position);
    if (!playing || !canFollow) return;

    const anchoredAt = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      setCurrentTime(position + (now - anchoredAt) / 1000);
      frame = requestAnimationFrame(tick);
    });

    return () => cancelAnimationFrame(frame);
  }, [position, playing, canFollow]);

  if (!lyrics) {
    return (
      <p className="text-sm text-text/45">
        {failed === songId ? 'Could not load the lyrics for this song.' : 'Loading lyrics...'}
      </p>
    );
  }

  if (canFollow) {
    return <LyricsFollower lines={lyrics.timings!.lines} currentTime={currentTime} />;
  }

  // No usable timings: show the words without the follow-along.
  if (lyrics.text.trim()) {
    return (
      <pre className="max-h-64 overflow-y-auto px-2 py-3 whitespace-pre-wrap font-sans text-base leading-relaxed text-text/80">
        {lyrics.text}
      </pre>
    );
  }

  return <p className="text-sm text-text/45">No lyrics for this song.</p>;
}
