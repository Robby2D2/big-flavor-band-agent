'use client';

import WaveformView from '../WaveformView';
import { formatTime } from '../audioEngine';
import type { StemPlaybackControl } from './useStemPlayback';
import type { FixEntry } from '@/hooks/useProcessingQueue';
import { FULL_MIX_STEM_ID } from '@/hooks/useProcessingQueue';
import { stemColor } from './stemColors';

interface StemInfo {
  id: number;
  name: string;
}

interface StemConsoleProps {
  /** Console rows: the full mix first, then each separated stem. */
  stems: StemInfo[];
  buffers: Record<number, AudioBuffer>;
  /** Rows whose audio is still being fetched/decoded. */
  loadingStemIds: Set<number>;
  controls: Record<number, StemPlaybackControl>;
  setControl: (id: number, patch: Partial<StemPlaybackControl>) => void;
  selectedStemId: number | null;
  onSelectStem: (id: number) => void;
  fixesForStem: (stemId: number) => FixEntry[];
  analyzedStemIds: Set<number>;
  analyzingStemIds: Set<number>;
  onAnalyzeStem: (stemId: number) => void;
  playing: boolean;
  playhead: number;
  maxDuration: number;
  onTogglePlay: () => void;
  onSeek: (seconds: number) => void;
  separating: boolean;
  analyzed: boolean;
  analysisNote: string | null;
  onReseparate: () => void;
}

function Spinner({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-block rounded-full border-2 border-signal/25 border-t-signal animate-spin ${className}`}
    />
  );
}

/**
 * The merged stem console: a transport across the whole song on top, then one
 * row per part — the full mix first, then each separated stem — with its own
 * chain of detected fixes as pills and mute/solo/gain. Picking a row here is
 * what scopes the fix queue below it, and the full mix is a row like any other
 * so the whole song can be played, analyzed and fixed alongside its parts.
 */
export default function StemConsole({
  stems,
  buffers,
  loadingStemIds,
  controls,
  setControl,
  selectedStemId,
  onSelectStem,
  fixesForStem,
  analyzedStemIds,
  analyzingStemIds,
  onAnalyzeStem,
  playing,
  playhead,
  maxDuration,
  onTogglePlay,
  onSeek,
  separating,
  analyzed,
  analysisNote,
  onReseparate,
}: StemConsoleProps) {
  const fullMixBuffer = buffers[FULL_MIX_STEM_ID] ?? null;
  const fullMixLoading = !fullMixBuffer && loadingStemIds.has(FULL_MIX_STEM_ID);

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
          disabled={maxDuration === 0}
          aria-label={playing ? 'Pause' : 'Play'}
          className="flex-none w-9 h-9 rounded-full bg-signal text-canvas flex items-center justify-center hover:opacity-90 disabled:opacity-40"
        >
          {playing ? (
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
        <div className="flex-1 min-w-0 relative">
          <WaveformView
            buffer={fullMixBuffer}
            duration={maxDuration}
            height={48}
            playhead={playhead}
            onSeek={onSeek}
            waveColor={stemColor('full mix')}
          />
          {fullMixLoading && (
            <span className="absolute inset-0 flex items-center justify-center gap-2 font-mono text-[10px] text-text/45">
              <Spinner className="w-3.5 h-3.5" />
              loading full track…
            </span>
          )}
        </div>
      </div>

      <div
        className={`flex flex-col gap-2 transition-opacity ${
          separating ? 'opacity-40 pointer-events-none select-none' : ''
        }`}
      >
        {stems.map((stem) => {
          const c = controls[stem.id];
          const selected = stem.id === selectedStemId;
          const isFullMix = stem.id === FULL_MIX_STEM_ID;
          const color = stemColor(stem.name);
          const fixes = fixesForStem(stem.id);
          const buffer = buffers[stem.id] ?? null;
          const loading = !buffer && loadingStemIds.has(stem.id);
          const rowAnalyzing = analyzingStemIds.has(stem.id);
          const rowAnalyzed = analyzedStemIds.has(stem.id);
          return (
            <div
              key={stem.id}
              onClick={() => onSelectStem(stem.id)}
              className={`rounded-lg border px-3 py-2.5 flex items-center gap-3 cursor-pointer transition-colors ${
                selected ? 'bg-white/[0.06] border-white/25' : 'bg-well border-white/7 hover:bg-white/[0.03]'
              } ${isFullMix ? 'border-dashed' : ''}`}
            >
              <div className="w-32 flex-none">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
                  <span className="font-semibold text-sm text-text capitalize">{stem.name}</span>
                </div>
                <div className="font-mono text-[10px] text-text/35 mt-0.5">
                  {loading
                    ? 'loading…'
                    : rowAnalyzing
                      ? 'analyzing…'
                      : fixes.length > 0
                        ? `${fixes.length} fix${fixes.length === 1 ? '' : 'es'}`
                        : rowAnalyzed
                          ? 'clean'
                          : isFullMix
                            ? 'whole song'
                            : 'not analyzed'}
                </div>
              </div>

              <div
                className="w-36 h-8 flex-none relative"
                onClick={(e) => e.stopPropagation()}
              >
                <WaveformView
                  buffer={buffer}
                  duration={maxDuration}
                  height={32}
                  playhead={playhead}
                  onSeek={onSeek}
                  waveColor={color}
                />
                {loading && (
                  <span className="absolute inset-0 flex items-center justify-center">
                    <Spinner className="w-3.5 h-3.5" />
                  </span>
                )}
              </div>

              <div className="flex-1 flex flex-wrap items-center gap-1.5 min-w-0">
                {rowAnalyzing ? (
                  <span className="flex items-center gap-1.5 font-mono text-[10px] text-text/45">
                    <Spinner className="w-3 h-3" />
                    analyzing…
                  </span>
                ) : fixes.length > 0 ? (
                  fixes.map((f) => (
                    <span
                      key={f.id}
                      className={`text-[10.5px] font-semibold px-2 py-0.5 rounded-md border ${
                        f.enabled
                          ? 'text-signal border-signal/35 bg-signal/10'
                          : 'text-text/35 border-white/10 bg-transparent'
                      }`}
                    >
                      {f.title}
                    </span>
                  ))
                ) : rowAnalyzed ? (
                  <span className="font-mono text-[10px] text-text/30">no fixes detected</span>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onAnalyzeStem(stem.id);
                    }}
                    disabled={separating}
                    className="text-[10.5px] font-semibold text-text/70 border border-white/14 rounded-md px-2 py-0.5 hover:bg-white/5 disabled:opacity-40"
                  >
                    Analyze {isFullMix ? 'full mix' : 'this stem'}
                  </button>
                )}
              </div>

              <div
                className="flex items-center gap-2 flex-none"
                onClick={(e) => e.stopPropagation()}
              >
                {rowAnalyzed && !rowAnalyzing && (
                  <button
                    onClick={() => onAnalyzeStem(stem.id)}
                    disabled={separating}
                    title="Re-analyze just this part"
                    className="font-mono text-[10px] px-1.5 py-0.5 rounded text-text/40 hover:text-text/70 disabled:opacity-40"
                  >
                    RE-ANALYZE
                  </button>
                )}
                <button
                  onClick={() => setControl(stem.id, { solo: !c?.solo })}
                  className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                    c?.solo ? 'text-attention' : 'text-text/40 hover:text-text/70'
                  }`}
                >
                  SOLO
                </button>
                <button
                  onClick={() => setControl(stem.id, { mute: !c?.mute })}
                  title={
                    isFullMix
                      ? 'The full mix starts muted — the stems below already add up to it. Un-mute or solo it to hear the mix itself.'
                      : undefined
                  }
                  className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                    c?.mute ? 'text-red-400' : 'text-text/40 hover:text-text/70'
                  }`}
                >
                  MUTE
                </button>
                <input
                  type="range"
                  min={0}
                  max={1.5}
                  step={0.05}
                  value={c?.gain ?? 1}
                  onChange={(e) => setControl(stem.id, { gain: Number(e.target.value) })}
                  className="w-16"
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
