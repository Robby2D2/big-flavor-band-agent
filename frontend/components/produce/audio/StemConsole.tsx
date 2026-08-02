'use client';

import WaveformView from '../WaveformView';
import { formatTime } from '../audioEngine';
import type { StemPlaybackControl } from './useStemPlayback';
import type { FixEntry } from '@/hooks/useProcessingQueue';
import { stemColor } from './stemColors';

interface StemInfo {
  id: number;
  name: string;
}

interface StemConsoleProps {
  stems: StemInfo[];
  buffers: Record<number, AudioBuffer>;
  controls: Record<number, StemPlaybackControl>;
  setControl: (id: number, patch: Partial<StemPlaybackControl>) => void;
  selectedStemId: number | null;
  onSelectStem: (id: number) => void;
  fixesForStem: (stemId: number) => FixEntry[];
  playing: boolean;
  playhead: number;
  maxDuration: number;
  onTogglePlay: () => void;
  separating: boolean;
  analyzed: boolean;
  analysisNote: string | null;
  onReseparate: () => void;
}

/**
 * The merged stem console: each separated stem's waveform, its own chain of
 * detected fixes as pills, and mute/solo/gain — all in one place, since
 * picking a stem here is what scopes the fix queue below it.
 */
export default function StemConsole({
  stems,
  buffers,
  controls,
  setControl,
  selectedStemId,
  onSelectStem,
  fixesForStem,
  playing,
  playhead,
  maxDuration,
  onTogglePlay,
  separating,
  analyzed,
  analysisNote,
  onReseparate,
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
                : 'Loaded from a previous run — press Start analysis above to detect fixes.'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-none">
          <span className="font-mono text-xs text-text/50 tabular-nums">
            {formatTime(playhead)} / {formatTime(maxDuration)}
          </span>
          <button
            onClick={onTogglePlay}
            className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-3 py-1.5 hover:bg-white/5"
          >
            {playing ? 'Stop' : 'Play stems'}
          </button>
          <button
            onClick={onReseparate}
            disabled={separating}
            className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-3 py-1.5 hover:bg-white/5 disabled:opacity-50"
          >
            {separating ? 'Re-separating…' : 'Re-separate'}
          </button>
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
          const color = stemColor(stem.name);
          const fixes = fixesForStem(stem.id);
          return (
            <div
              key={stem.id}
              onClick={() => onSelectStem(stem.id)}
              className={`rounded-lg border px-3 py-2.5 flex items-center gap-3 cursor-pointer transition-colors ${
                selected ? 'bg-white/[0.06] border-white/25' : 'bg-well border-white/7 hover:bg-white/[0.03]'
              }`}
            >
              <div className="w-32 flex-none">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
                  <span className="font-semibold text-sm text-text capitalize">{stem.name}</span>
                </div>
                <div className="font-mono text-[10px] text-text/35 mt-0.5">
                  {fixes.length > 0
                    ? `${fixes.length} fix${fixes.length === 1 ? '' : 'es'}`
                    : analyzed
                      ? 'clean'
                      : 'not analyzed yet'}
                </div>
              </div>

              <div className="w-36 h-8 flex-none" onClick={(e) => e.stopPropagation()}>
                <WaveformView
                  buffer={buffers[stem.id] ?? null}
                  duration={maxDuration}
                  height={32}
                  playhead={playing ? playhead : null}
                  waveColor={color}
                />
              </div>

              <div className="flex-1 flex flex-wrap gap-1.5 min-w-0">
                {fixes.length === 0 ? (
                  <span className="font-mono text-[10px] text-text/30">
                    {analyzed ? 'no fixes detected' : 'not analyzed yet'}
                  </span>
                ) : (
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
                )}
              </div>

              <div
                className="flex items-center gap-2 flex-none"
                onClick={(e) => e.stopPropagation()}
              >
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
