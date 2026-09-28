'use client';

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
  selectedStemId: number | null;
  onSelectStem: (id: number) => void;
  fixesForStem: (stemId: number) => FixEntry[];
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
 * separated stem. Picking a row here is what scopes the fix queue below it, and
 * the full mix is a row like any other so the whole song can be played,
 * analyzed and fixed alongside its parts. The player sits just above it, in
 * TransportBar, so it stays in view while the rows scroll.
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
                ? 'Each stem is analyzed on its own — a hiss fix that saves the vocal can wreck the cymbals.'
                : 'Loaded from a previous run — press Start analysis above, or analyze one part at a time. Separate stems (also above) makes a fresh set.'}
          </p>
        </div>
      </div>

      {/* A row's name column and meter are fixed-width on purpose — the console
          is read by comparing those columns down the rows — so on a phone the
          row is simply wider than the screen. Scrolling that here keeps the
          document itself from scrolling sideways and taking the header with it.
          The player (TransportBar) is outside the console altogether, so Play
          and the clock remain in place while the rows are scrolled. */}
      <div className="overflow-x-auto" data-testid="stem-rows-scroll">
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
    </div>
  );
}
