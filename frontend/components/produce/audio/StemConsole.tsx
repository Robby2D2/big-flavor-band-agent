'use client';

import WaveformView from '../WaveformView';
import { formatTime } from '../audioEngine';
import type { StemPlaybackControl } from './useStemPlayback';
import type { WaveformPeaks } from '../audioEngine';
import type { FixEntry, StemInfo } from '@/hooks/useProcessingQueue';
import { FULL_MIX_STEM_ID } from '@/hooks/useProcessingQueue';
import { stemColor } from './stemColors';
import Spinner from './Spinner';
import StemRow from './StemRow';

interface StemConsoleProps {
  /** Console rows: the full mix first, then each separated stem. */
  stems: StemInfo[];
  /** Server-computed drawing envelopes, keyed by row id. */
  peaks: Record<number, WaveformPeaks>;
  /** Rows whose waveform is still being fetched. */
  peaksLoadingIds: Set<number>;
  /** Whether any playback audio has decoded yet — the transport needs one. */
  playbackReady: boolean;
  controls: Record<number, StemPlaybackControl>;
  setControl: (id: number, patch: Partial<StemPlaybackControl>) => void;
  selectedStemId: number | null;
  onSelectStem: (id: number) => void;
  fixesForStem: (stemId: number) => FixEntry[];
  analyzedStemIds: Set<number>;
  analyzingStemIds: Set<number>;
  onAnalyzeStem: (stemId: number) => void;
  identifyingStemIds: Set<number>;
  onIdentifyStem: (stemId: number) => void;
  onRenameStem: (stemId: number, displayName: string) => void;
  playing: boolean;
  playhead: number;
  maxDuration: number;
  onTogglePlay: () => void;
  /** A fix chain is being rendered before playback can start. */
  renderingFixes: boolean;
  onSeek: (seconds: number) => void;
  separating: boolean;
  analyzed: boolean;
  analysisNote: string | null;
  onReseparate: () => void;
}

/**
 * The merged stem console: a transport across the whole song on top, then one
 * row per part — the full mix first, then each separated stem. Picking a row
 * here is what scopes the fix queue below it, and the full mix is a row like
 * any other so the whole song can be played, analyzed and fixed alongside its
 * parts.
 */
export default function StemConsole({
  stems,
  peaks,
  peaksLoadingIds,
  playbackReady,
  controls,
  setControl,
  selectedStemId,
  onSelectStem,
  fixesForStem,
  analyzedStemIds,
  analyzingStemIds,
  onAnalyzeStem,
  identifyingStemIds,
  onIdentifyStem,
  onRenameStem,
  playing,
  playhead,
  maxDuration,
  onTogglePlay,
  renderingFixes,
  onSeek,
  separating,
  analyzed,
  analysisNote,
  onReseparate,
}: StemConsoleProps) {
  const fullMixPeaks = peaks[FULL_MIX_STEM_ID]?.peaks ?? null;
  const fullMixLoading = !fullMixPeaks && peaksLoadingIds.has(FULL_MIX_STEM_ID);

  return (
    <div className="bg-raised border border-white/8 rounded-xl p-4 relative">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-text">Stem console</h3>
            {separating ? (
              <span className="flex items-center gap-1.5 font-mono text-[9.5px] tracking-wide text-attention bg-attention/15 px-1.5 py-0.5 rounded">
                <span className="w-1.5 h-1.5 rounded-full bg-attention animate-pulse" />
                ANALYZING…
              </span>
            ) : analyzed ? (
              <span className="font-mono text-[9.5px] tracking-wide text-confirm bg-confirm/15 px-1.5 py-0.5 rounded">
                SEPARATED · ANALYZED
              </span>
            ) : (
              <span className="font-mono text-[9.5px] tracking-wide text-text/50 bg-white/8 px-1.5 py-0.5 rounded">
                SEPARATED
              </span>
            )}
          </div>
          <p className="text-xs text-text/45 mt-1">
            {separating
              ? analysisNote ?? 'Analyzing — the stems and fixes below are from the previous run.'
              : analyzed
                ? 'Each stem is analyzed on its own — a hiss fix that saves the vocal can wreck the cymbals.'
                : 'Loaded from a previous run — press Start analysis above, or analyze one part at a time.'}
          </p>
        </div>
        <button
          onClick={onReseparate}
          disabled={separating}
          className="flex-none text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-3 py-1.5 hover:bg-white/5 disabled:opacity-50"
        >
          {separating ? 'Re-separating…' : 'Re-separate'}
        </button>
      </div>

      {/* Transport: the whole song's waveform, with a playhead you can click or
          drag to scrub. Play here drives every un-muted row in sync. */}
      <div className="flex items-center gap-3 bg-well border border-white/7 rounded-lg px-3 py-2.5 mb-3">
        <button
          onClick={onTogglePlay}
          // The waveforms arrive well before the audio does, so without the
          // playbackReady gate the button would look live and do nothing.
          disabled={maxDuration === 0 || !playbackReady || renderingFixes}
          aria-label={
            playing ? 'Pause' : renderingFixes ? 'Rendering fixes' : playbackReady ? 'Play' : 'Preparing playback'
          }
          className="flex-none w-9 h-9 rounded-full bg-signal text-canvas flex items-center justify-center hover:opacity-90 disabled:opacity-40"
        >
          {renderingFixes || (maxDuration > 0 && !playbackReady) ? (
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
        <span className="flex-none font-mono text-xs text-text/55 tabular-nums">
          {formatTime(playhead)} / {formatTime(maxDuration)}
        </span>
        {renderingFixes && (
          <span className="flex-none font-mono text-[10px] text-attention">rendering fixes…</span>
        )}
        <div className="flex-1 min-w-0 relative">
          <WaveformView
            peaks={fullMixPeaks}
            duration={maxDuration}
            height={48}
            playhead={playhead}
            onSeek={onSeek}
            waveColor={stemColor('full mix')}
          />
          {fullMixLoading && (
            <span className="absolute inset-0 flex items-center justify-center gap-2 font-mono text-[10px] text-text/45">
              <Spinner className="w-3.5 h-3.5" />
              loading waveform…
            </span>
          )}
        </div>
      </div>

      <div
        className={`flex flex-col gap-2 transition-opacity ${
          separating ? 'opacity-40 pointer-events-none select-none' : ''
        }`}
      >
        {stems.filter((stem) => !stem.silent).map((stem) => (
          <StemRow
            key={stem.id}
            stem={stem}
            peaks={peaks[stem.id]?.peaks ?? null}
            loading={!peaks[stem.id] && peaksLoadingIds.has(stem.id)}
            control={controls[stem.id]}
            setControl={(patch) => setControl(stem.id, patch)}
            selected={stem.id === selectedStemId}
            onSelect={() => onSelectStem(stem.id)}
            fixes={fixesForStem(stem.id)}
            analyzed={analyzedStemIds.has(stem.id)}
            analyzing={analyzingStemIds.has(stem.id)}
            onAnalyze={() => onAnalyzeStem(stem.id)}
            identifying={identifyingStemIds.has(stem.id)}
            onIdentify={() => onIdentifyStem(stem.id)}
            onRename={(displayName) => onRenameStem(stem.id, displayName)}
            playhead={playhead}
            maxDuration={maxDuration}
            onSeek={onSeek}
            disabled={separating}
          />
        ))}
      </div>
    </div>
  );
}
