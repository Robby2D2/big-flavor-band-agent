'use client';

import { useEffect, useState } from 'react';
import LyricsFollower from '../../LyricsFollower';
import { LyricTimings, TimedLyricsResponse, isFollowable } from '@/lib/lyricTimings';
import WaveformView from '../WaveformView';
import { formatTime } from '../audioEngine';
import type { Peaks } from '../audioEngine';
import { stemColor } from './stemColors';
import Spinner from './Spinner';

interface TransportBarProps {
  /** The full mix's waveform — the whole song, which is what the bar scrubs. */
  peaks: Peaks | null;
  peaksLoading: boolean;
  /** Whether any playback audio has decoded yet — play needs one. */
  playbackReady: boolean;
  /**
   * Rows' playback audio still arriving: how many have decoded, and how much of
   * the rest has downloaded (null when the server gave no sizes).
   */
  audioLoading: { ready: number; total: number; fraction: number | null } | null;
  playing: boolean;
  playhead: number;
  maxDuration: number;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  /** Audible rows whose enabled fixes have not been rendered, so play raw. */
  unrenderedRows: string[];
  /** Whether those rows' fixes are rendering right now. */
  renderingFixes: boolean;
  /** Some audible row has fixes, and every such row is playing them. */
  withFixes: boolean;
  /** The song whose follow-along lyrics the Lyrics toggle shows. */
  songId: number;
  /** Every fix is bypassed, so the whole song plays as recorded. */
  fixesBypassed?: boolean;
  /** Flip the bypass; omitted while there are no fixes to bypass. */
  onToggleBypass?: () => void;
  /**
   * Some audible row has its fixed audio in hand. Until then bypassing would
   * play the same original audio, so the switch waits rather than look live.
   */
  fixesReady?: boolean;
}

/**
 * The page's one player: play, the clock, the whole song's waveform to scrub,
 * and the Fixes switch. It lives in the version card, which stays in view while
 * the console rows scroll, so it is always at hand.
 *
 * Play works as soon as any audio has decoded — it never waits for fixes to
 * render. Rows whose fixes are not ready play as recorded, and the bar says so
 * plainly, until the rendered audio swaps in where the playhead is.
 *
 * The Fixes switch is the whole-song A/B: it changes what is heard at the
 * playhead and nothing else — which fixes are on, and so what a save would
 * contain, is left exactly as it was.
 */
export default function TransportBar({
  peaks,
  peaksLoading,
  playbackReady,
  audioLoading,
  playing,
  playhead,
  maxDuration,
  onTogglePlay,
  onSeek,
  unrenderedRows,
  renderingFixes,
  withFixes,
  songId,
  fixesBypassed = false,
  onToggleBypass,
  fixesReady = true,
}: TransportBarProps) {
  // Fetched each time the panel opens, not once: the point of it here is to
  // check a re-extraction, which lands while the page stays open.
  const [showLyrics, setShowLyrics] = useState(false);
  const [timings, setTimings] = useState<LyricTimings | null | undefined>(undefined);
  useEffect(() => {
    if (!showLyrics) return;
    let cancelled = false;
    fetch(`/api/songs/${songId}/lyrics/timed`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: TimedLyricsResponse | null) => {
        if (!cancelled) setTimings(data?.timings ?? null);
      })
      .catch(() => {
        if (!cancelled) setTimings(null);
      });
    return () => {
      cancelled = true;
    };
  }, [showLyrics, songId]);

  const waiting = maxDuration > 0 && !playbackReady;
  // A bypass already on can always be turned off; one not yet on has nothing
  // to compare against until some fixed audio has arrived.
  const switchWaiting = !fixesBypassed && !fixesReady;
  const fixesOn = !fixesBypassed && fixesReady;

  let hearing: { text: string; tone: string } | null = null;
  if (audioLoading) {
    const parts = `${audioLoading.ready} of ${audioLoading.total} parts ready`;
    hearing = {
      text:
        audioLoading.fraction === null
          ? `Loading audio · ${parts}`
          : audioLoading.fraction < 1
            ? `Loading audio ${Math.floor(audioLoading.fraction * 100)}% · ${parts}`
            : `Decoding audio · ${parts}`,
      tone: 'text-text/55',
    };
  } else if (fixesBypassed) {
    hearing = { text: 'Fixes bypassed · hearing the original', tone: 'text-text/55' };
  } else if (unrenderedRows.length > 0) {
    hearing = {
      text: `Original audio on ${unrenderedRows.join(', ')} · ${
        renderingFixes ? 'fixes rendering…' : 'fixes not rendered yet'
      }`,
      tone: 'text-attention',
    };
  } else if (withFixes) {
    hearing = { text: 'With fixes', tone: 'text-confirm' };
  }

  return (
    <div className="rounded-lg border border-white/6 bg-well/60 px-3 py-2.5">
      <div className="flex items-center gap-3">
        <button
          onClick={onTogglePlay}
          // The waveforms arrive well before the audio does, so without the
          // playbackReady gate the button would look live and do nothing.
          disabled={maxDuration === 0 || !playbackReady}
          aria-label={
            playing ? 'Pause' : playbackReady ? 'Play' : 'Preparing playback'
          }
          className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-signal text-canvas hover:opacity-90 disabled:opacity-40"
        >
          {waiting ? (
            <Spinner className="w-3.5 h-3.5" />
          ) : playing ? (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              <rect x="1.5" y="1" width="3.25" height="10" rx="0.75" />
              <rect x="7.25" y="1" width="3.25" height="10" rx="0.75" />
            </svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              <path d="M2.5 1.4a.6.6 0 0 1 .92-.5l6.6 4.6a.6.6 0 0 1 0 1l-6.6 4.6a.6.6 0 0 1-.92-.5V1.4Z" />
            </svg>
          )}
        </button>
        <span className="flex-none font-mono text-xs tabular-nums text-text/55">
          {formatTime(playhead)} / {formatTime(maxDuration)}
        </span>
        <div className="relative min-w-0 flex-1">
          <WaveformView
            peaks={peaks}
            duration={maxDuration}
            height={48}
            playhead={playhead}
            onSeek={onSeek}
            waveColor={stemColor('full mix')}
          />
          {peaksLoading && (
            <span className="absolute inset-0 flex items-center justify-center gap-2 font-mono text-[10px] text-text/45">
              <Spinner className="w-3.5 h-3.5" />
              loading waveform…
            </span>
          )}
        </div>
        {onToggleBypass && (
          <button
            onClick={onToggleBypass}
            disabled={switchWaiting}
            role="switch"
            aria-checked={fixesOn}
            aria-label="Fixes"
            title={
              switchWaiting
                ? 'The fixes are still rendering — the original is what is playing'
                : fixesBypassed
                  ? 'Hear the song with its fixes'
                  : 'Hear the song as recorded — your fix choices stay as they are'
            }
            className="flex flex-none items-center gap-1.5 disabled:cursor-not-allowed"
          >
            {switchWaiting && renderingFixes && <Spinner className="h-3 w-3 text-text/40" />}
            <span
              className={`font-mono text-[10.5px] font-semibold ${
                fixesOn ? 'text-confirm' : 'text-text/40'
              }`}
            >
              FIXES
            </span>
            <span
              className={`relative h-[18px] w-8 rounded-full transition-colors ${
                fixesOn ? 'bg-confirm' : 'bg-white/13'
              } ${switchWaiting ? 'opacity-50' : ''}`}
            >
              <span
                className={`absolute top-0.5 h-[14px] w-[14px] rounded-full transition-all ${
                  fixesOn ? 'right-0.5 bg-canvas' : 'left-0.5 bg-text/55'
                }`}
              />
            </span>
          </button>
        )}
        <button
          onClick={() => {
            setTimings(undefined);
            setShowLyrics((v) => !v);
          }}
          aria-pressed={showLyrics}
          className={`flex-none rounded-full border px-3 py-1 text-xs ${
            showLyrics ? 'border-signal text-signal' : 'border-white/15 text-text/55 hover:text-text'
          }`}
        >
          Lyrics
        </button>
      </div>
      {showLyrics &&
        (isFollowable(timings) ? (
          <LyricsFollower
            lines={timings!.lines}
            currentTime={playhead}
            onSeek={onSeek}
            className="mt-2 border-t border-white/8"
          />
        ) : (
          <p className="mt-2 border-t border-white/8 pt-2 pl-12 text-[11px] text-text/45" data-testid="transport-lyrics-note">
            {timings === undefined
              ? 'Loading lyrics…'
              : timings?.status === 'stale'
                ? 'The lyrics were edited after extraction, so their timings no longer match — re-extract to follow along.'
                : 'No follow-along timings yet — extract the lyrics below.'}
          </p>
        ))}
      {hearing && (
        <p className={`mt-1.5 truncate pl-12 text-[11px] ${hearing.tone}`} data-testid="transport-hearing">
          {hearing.text}
        </p>
      )}
    </div>
  );
}
