'use client';

import { useEffect, useRef, useState } from 'react';
import WaveformView from '../WaveformView';
import type { StemPlaybackControl } from './useStemPlayback';
import type { FixEntry, StemInfo } from '@/hooks/useProcessingQueue';
import { FULL_MIX_STEM_ID, stemLabel } from '@/hooks/useProcessingQueue';
import { stemColor } from './stemColors';
import Spinner from './Spinner';

interface StemRowProps {
  stem: StemInfo;
  buffer: AudioBuffer | null;
  loading: boolean;
  control: StemPlaybackControl | undefined;
  setControl: (patch: Partial<StemPlaybackControl>) => void;
  selected: boolean;
  onSelect: () => void;
  fixes: FixEntry[];
  analyzed: boolean;
  analyzing: boolean;
  onAnalyze: () => void;
  identifying: boolean;
  onIdentify: () => void;
  onRename: (displayName: string) => void;
  playhead: number;
  maxDuration: number;
  onSeek: (seconds: number) => void;
  disabled: boolean;
}

/**
 * One row of the stem console: what this part *is* (its label and the
 * instruments heard in it), its waveform, its chain of detected fixes, and its
 * mix controls.
 *
 * The identity block matters more than it looks: Demucs' source list is fixed
 * by the model, so a banjo or mandolin arrives labelled "other". The tagger's
 * guess and the producer's own rename are how that stem gets a name a human
 * recognises.
 */
export default function StemRow({
  stem,
  buffer,
  loading,
  control,
  setControl,
  selected,
  onSelect,
  fixes,
  analyzed,
  analyzing,
  onAnalyze,
  identifying,
  onIdentify,
  onRename,
  playhead,
  maxDuration,
  onSeek,
  disabled,
}: StemRowProps) {
  const isFullMix = stem.id === FULL_MIX_STEM_ID;
  const color = stemColor(stem.name);
  const label = stemLabel(stem);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(label);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  const commit = () => {
    setEditing(false);
    // Typing the Demucs name back in is the same as clearing the override.
    if (draft.trim() !== label) onRename(draft.trim() === stem.name ? '' : draft);
  };

  return (
    <div
      onClick={onSelect}
      className={`rounded-lg border px-3 py-2.5 flex items-center gap-3 cursor-pointer transition-colors ${
        selected ? 'bg-white/[0.06] border-white/25' : 'bg-well border-white/7 hover:bg-white/[0.03]'
      } ${isFullMix ? 'border-dashed' : ''}`}
    >
      <div className="w-44 flex-none min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="w-2 h-2 rounded-sm flex-none" style={{ background: color }} />
          {editing ? (
            <input
              ref={inputRef}
              value={draft}
              autoFocus
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setDraft(e.target.value)}
              onBlur={commit}
              onKeyDown={(e) => {
                if (e.key === 'Enter') commit();
                if (e.key === 'Escape') {
                  setDraft(label);
                  setEditing(false);
                }
              }}
              maxLength={64}
              className="w-full bg-canvas border border-signal/50 rounded px-1.5 py-0.5 text-sm text-text outline-none"
            />
          ) : (
            <>
              <span className="font-semibold text-sm text-text capitalize truncate">{label}</span>
              {/* Once relabelled, keep what Demucs actually produced visible —
                  the fix tools still reason about the source stem. */}
              {stem.displayName && (
                <span className="font-mono text-[9.5px] text-text/30 flex-none">{stem.name}</span>
              )}
              {!isFullMix && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDraft(label);
                    setEditing(true);
                  }}
                  title="Rename this stem"
                  className="flex-none font-mono text-[10px] text-text/30 hover:text-text/70"
                >
                  ✎
                </button>
              )}
            </>
          )}
        </div>

        <div className="font-mono text-[10px] text-text/35 mt-0.5 truncate">
          {loading ? (
            'loading…'
          ) : analyzing ? (
            'analyzing…'
          ) : identifying ? (
            'identifying…'
          ) : isFullMix ? (
            'whole song'
          ) : stem.silent ? (
            <span className="text-text/25">silent — nothing in this stem</span>
          ) : stem.instruments.length > 0 ? (
            <span title={stem.instruments.map((i) => `${i.label} ${i.score}`).join(', ')}>
              {stem.instruments.map((i) => i.label).join(' · ')}
            </span>
          ) : stem.tagged ? (
            'no instrument recognised'
          ) : (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onIdentify();
              }}
              className="font-mono text-[10px] text-signal/70 hover:text-signal underline underline-offset-2"
            >
              identify instruments
            </button>
          )}
        </div>
      </div>

      <div className="w-36 h-8 flex-none relative" onClick={(e) => e.stopPropagation()}>
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
        {analyzing ? (
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
        ) : analyzed ? (
          <span className="font-mono text-[10px] text-text/30">no fixes detected</span>
        ) : (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAnalyze();
            }}
            disabled={disabled}
            className="text-[10.5px] font-semibold text-text/70 border border-white/14 rounded-md px-2 py-0.5 hover:bg-white/5 disabled:opacity-40"
          >
            Analyze {isFullMix ? 'full mix' : 'this stem'}
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 flex-none" onClick={(e) => e.stopPropagation()}>
        {analyzed && !analyzing && (
          <button
            onClick={onAnalyze}
            disabled={disabled}
            title="Re-analyze just this part"
            className="font-mono text-[10px] px-1.5 py-0.5 rounded text-text/40 hover:text-text/70 disabled:opacity-40"
          >
            RE-ANALYZE
          </button>
        )}
        <button
          onClick={() => setControl({ solo: !control?.solo })}
          className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
            control?.solo ? 'text-attention' : 'text-text/40 hover:text-text/70'
          }`}
        >
          SOLO
        </button>
        <button
          onClick={() => setControl({ mute: !control?.mute })}
          title={
            isFullMix
              ? 'The full mix starts muted — the stems below already add up to it. Un-mute or solo it to hear the mix itself.'
              : undefined
          }
          className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
            control?.mute ? 'text-red-400' : 'text-text/40 hover:text-text/70'
          }`}
        >
          MUTE
        </button>
        <input
          type="range"
          min={0}
          max={1.5}
          step={0.05}
          value={control?.gain ?? 1}
          onChange={(e) => setControl({ gain: Number(e.target.value) })}
          className="w-16"
        />
      </div>
    </div>
  );
}
