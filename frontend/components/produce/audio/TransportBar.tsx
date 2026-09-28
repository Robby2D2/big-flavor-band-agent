'use client';

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
  playing: boolean;
  playhead: number;
  maxDuration: number;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  /** Hear it is waiting for its own fix to render before it can play it. */
  auditionRendering: boolean;
  /** What a fix card started, when it did. */
  audition: { fixTitle: string; rowName: string } | null;
  /** Audible rows whose enabled fixes have not been rendered, so play raw. */
  unrenderedRows: string[];
  /** Whether those rows' fixes are rendering right now. */
  renderingFixes: boolean;
  /** Some audible row has fixes, and every such row is playing them. */
  withFixes: boolean;
}

/**
 * The page's one player: play, the clock, and the whole song's waveform to
 * scrub. It sits above the stem console and stays in view while the rows
 * scroll, so it is always at hand; the version panel's own player is gone.
 *
 * Play works as soon as any audio has decoded — it never waits for fixes to
 * render. Rows whose fixes are not ready play as recorded, and the bar says so
 * plainly, until the rendered audio swaps in where the playhead is.
 */
export default function TransportBar({
  peaks,
  peaksLoading,
  playbackReady,
  playing,
  playhead,
  maxDuration,
  onTogglePlay,
  onSeek,
  auditionRendering,
  audition,
  unrenderedRows,
  renderingFixes,
  withFixes,
}: TransportBarProps) {
  const waiting = maxDuration > 0 && !playbackReady;

  let hearing: { text: string; tone: string } | null = null;
  if (audition && !auditionRendering) {
    hearing = { text: `Auditioning ${audition.fixTitle} on ${audition.rowName}, fixes on`, tone: 'text-signal' };
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
    <div className="sticky top-0 z-30 rounded-xl border border-white/8 bg-raised/95 px-3 py-2.5 backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          onClick={onTogglePlay}
          // The waveforms arrive well before the audio does, so without the
          // playbackReady gate the button would look live and do nothing.
          disabled={maxDuration === 0 || !playbackReady || auditionRendering}
          aria-label={
            playing ? 'Pause' : auditionRendering ? 'Rendering fix' : playbackReady ? 'Play' : 'Preparing playback'
          }
          className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-signal text-canvas hover:opacity-90 disabled:opacity-40"
        >
          {auditionRendering || waiting ? (
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
      </div>
      {hearing && (
        <p className={`mt-1.5 truncate pl-12 text-[11px] ${hearing.tone}`} data-testid="transport-hearing">
          {hearing.text}
        </p>
      )}
    </div>
  );
}
