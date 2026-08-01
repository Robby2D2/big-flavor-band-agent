'use client';

import { useEffect, useState } from 'react';
import WaveformView from '../WaveformView';
import { formatTime, Region } from '../audioEngine';
import { stemColor } from './stemColors';

interface StemDetailPanelProps {
  stemId: number;
  stemName: string;
  buffer: AudioBuffer | null;
  duration: number;
  region: Region | null;
  onRegionChange: (region: Region | null) => void;
  enabledFixCount: number;
  onPreviewChain: () => Promise<string>;
}

/**
 * The selected stem's own waveform: drag a region to scope the fix queue
 * below to it, and A/B the stem as-recorded against its enabled fix chain
 * rendered on demand (there's no live preview — chain-applying is real DSP
 * work, so "B" is fetched only when asked for).
 */
export default function StemDetailPanel({
  stemId,
  stemName,
  buffer,
  duration,
  region,
  onRegionChange,
  enabledFixCount,
  onPreviewChain,
}: StemDetailPanelProps) {
  const [mode, setMode] = useState<'A' | 'B'>('A');
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const color = stemColor(stemName);

  // Selecting a different stem, or changing which fixes are enabled,
  // invalidates any previously rendered "with fixes" preview.
  useEffect(() => {
    setPreviewPath(null);
    setMode('A');
  }, [stemId, enabledFixCount]);

  const handleShowFixes = async () => {
    if (previewPath) {
      setMode('B');
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const path = await onPreviewChain();
      setPreviewPath(path);
      setMode('B');
    } catch (err) {
      setPreviewError((err as Error).message);
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <div className="bg-raised border border-signal/20 rounded-xl p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5">
          <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
          <h3 className="font-semibold text-text capitalize">{stemName}</h3>
          <div className="flex p-0.5 bg-well border border-white/8 rounded-lg">
            <button
              onClick={() => setMode('A')}
              className={`font-mono text-[10.5px] font-semibold px-2.5 py-1 rounded-md ${
                mode === 'A' ? 'bg-confirm text-canvas' : 'text-text/50'
              }`}
            >
              A · as recorded
            </button>
            <button
              onClick={handleShowFixes}
              disabled={enabledFixCount === 0 || previewLoading}
              className={`font-mono text-[10.5px] font-semibold px-2.5 py-1 rounded-md disabled:opacity-40 ${
                mode === 'B' ? 'bg-confirm text-canvas' : 'text-text/50'
              }`}
            >
              {previewLoading ? 'Rendering…' : `B · with fixes${enabledFixCount ? ` (${enabledFixCount})` : ''}`}
            </button>
          </div>
        </div>
      </div>

      {previewError && <p className="text-xs text-red-400 mb-2">{previewError}</p>}

      <WaveformView
        buffer={buffer}
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

      <audio
        controls
        preload="none"
        src={
          mode === 'B' && previewPath
            ? `/api/produce/clean/preview?path=${encodeURIComponent(previewPath)}`
            : `/api/produce/stems/${stemId}/audio`
        }
        className="w-full h-9 mt-3"
      />
    </div>
  );
}
