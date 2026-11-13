'use client';

import type { ReactNode } from 'react';
import type { StemPlaybackControl } from './useStemPlayback';
import type { WaveformPeaks } from '../audioEngine';
import type { FixEntry, StemInfo } from '@/hooks/useProcessingQueue';
import StemRow from './StemRow';

interface StemConsoleProps {
  /** Console rows: the full mix first, then each separated stem. */
  stems: StemInfo[];
  /** Server-computed drawing envelopes, keyed by row id. */
  peaks: Record<number, WaveformPeaks>;
  /** Rows whose waveform is still being fetched. */
  peaksLoadingIds: Set<number>;
  controls: Record<number, StemPlaybackControl>;
  setControl: (id: number, patch: Partial<StemPlaybackControl>) => void;
  /** The open row — its fix cards show beneath it. */
  selectedStemId: number | null;
  /** Open a row, or close them all with null. */
  onSelectStem: (id: number | null) => void;
  fixesForStem: (stemId: number) => FixEntry[];
  /** A row's switch: all its fixes off, or back on. */
  onSetRowFixesEnabled?: (stemId: number, enabled: boolean) => void;
  /** What the open row shows beneath it: its fix cards. */
  renderFixes?: (stem: StemInfo) => ReactNode;
  analyzedStemIds: Set<number>;
  analyzingStemIds: Set<number>;
  onAnalyzeStem: (stemId: number) => void;
  identifyingStemIds: Set<number>;
  onIdentifyStem: (stemId: number) => void;
  onRenameStem: (stemId: number, displayName: string) => void;
  playhead: number;
  maxDuration: number;
  onSeek: (seconds: number) => void;
  separating: boolean;
  analyzed: boolean;
  analysisNote: string | null;
}

/**
 * The merged stem console: one row per part — the full mix first, then each
 * separated stem. Clicking a row opens its fix cards beneath it; the full mix
 * is a row like any other, and its cards are the master fixes (trim, tone,
 * loudness), so the whole song is analyzed and fixed alongside its parts. The
 * player sits above it, in the version card, so it stays in view while the
 * rows scroll.
 */
export default function StemConsole({
  stems,
  peaks,
  peaksLoadingIds,
  controls,
  setControl,
  selectedStemId,
  onSelectStem,
  fixesForStem,
  onSetRowFixesEnabled,
  renderFixes,
  analyzedStemIds,
  analyzingStemIds,
  onAnalyzeStem,
  identifyingStemIds,
  onIdentifyStem,
  onRenameStem,
  playhead,
  maxDuration,
  onSeek,
  separating,
  analyzed,
  analysisNote,
}: StemConsoleProps) {
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
                ? 'Each stem is analyzed on its own — a hiss fix that saves the vocal can wreck the cymbals. Open a row to review its fixes.'
                : 'Loaded from a previous run — press Start analysis above, or analyze one part at a time. Separate stems (also above) makes a fresh set.'}
          </p>
        </div>
      </div>

      {/* A row's name column and meter are fixed-width on purpose — the console
          is read by comparing those columns down the rows — so on a phone the
          row is simply wider than the screen. Scrolling that here keeps the
          document itself from scrolling sideways and taking the header with it.
          The player (TransportBar) is outside the console altogether, so Play
          and the clock remain in place while the rows are scrolled. The open
          row's fix cards are not columns, so they are held to the visible width
          and pinned there (100cqw is this scroll box's own width). */}
      <div className="overflow-x-auto [container-type:inline-size]" data-testid="stem-rows-scroll">
        <div
          className={`flex flex-col gap-2 min-w-[40rem] transition-opacity ${
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
              onSelect={() => onSelectStem(stem.id === selectedStemId ? null : stem.id)}
              fixes={fixesForStem(stem.id)}
              onSetFixesEnabled={
                onSetRowFixesEnabled && ((enabled) => onSetRowFixesEnabled(stem.id, enabled))
              }
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
            >
              {renderFixes && (
                <div className="sticky left-0 w-[calc(100cqw_-_2px)] max-w-full border-t border-white/8 px-3 pt-3 pb-3.5">
                  {renderFixes(stem)}
                </div>
              )}
            </StemRow>
          ))}
        </div>
      </div>
    </div>
  );
}
