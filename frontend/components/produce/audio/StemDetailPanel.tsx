'use client';

import WaveformView from '../WaveformView';
import { formatTime, Peaks, Region } from '../audioEngine';
import { stemColor } from './stemColors';

interface StemDetailPanelProps {
  /** What to call this stem — the producer's label when they've set one. */
  stemName: string;
  /** The Demucs source name, which is what the color scheme is keyed on. */
  sourceName: string;
  peaks: Peaks | null;
  duration: number;
  region: Region | null;
  onRegionChange: (region: Region | null) => void;
  enabledFixCount: number;
}

/**
 * The selected stem's own waveform: drag a region to scope the fix queue below
 * it to part of the song.
 *
 * There is deliberately no player here. This panel used to A/B the stem
 * as-recorded against its rendered fix chain, which meant a second transport
 * playing the same audio as the console's — two players, unsynchronised, for
 * one song. The console transport is now the only one, and it plays the fix
 * chain itself, so "with fixes" is what you hear rather than something you
 * switch to.
 */
export default function StemDetailPanel({
  stemName,
  sourceName,
  peaks,
  duration,
  region,
  onRegionChange,
  enabledFixCount,
}: StemDetailPanelProps) {
  const color = stemColor(sourceName);

  return (
    <div className="bg-raised border border-signal/20 rounded-xl p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
          <h3 className="font-semibold text-text capitalize">{stemName}</h3>
          {enabledFixCount > 0 && (
            <span className="font-mono text-[9.5px] tracking-wide text-confirm bg-confirm/15 px-1.5 py-0.5 rounded">
              {enabledFixCount} FIX{enabledFixCount === 1 ? '' : 'ES'} · HEARD IN THE TRANSPORT
            </span>
          )}
        </div>
      </div>

      <WaveformView
        peaks={peaks}
        duration={duration}
        selectable
        region={region}
        onRegionChange={onRegionChange}
        waveColor={color}
        height={108}
      />

      <div className="flex items-center justify-between mt-2">
        {region ? (
          <span className="font-mono text-[10.5px] text-signal">
            REGION {formatTime(region.start)} – {formatTime(region.end)} · fixes below apply here only
          </span>
        ) : (
          <span className="font-mono text-[10.5px] text-text/35">
            Whole stem — drag on the waveform to limit fixes to a region.
          </span>
        )}
        {region && (
          <button
            onClick={() => onRegionChange(null)}
            className="font-mono text-[10.5px] text-text/40 hover:text-text/70"
          >
            clear region → whole stem
          </button>
        )}
      </div>
    </div>
  );
}
