'use client';

import { useState } from 'react';
import type { FixEntry } from '@/hooks/useProcessingQueue';
import { CONFIDENCE_COLOR, CONFIDENCE_LABEL } from './stemColors';

interface FixCardProps {
  fix: FixEntry;
  index: number;
  onToggle: () => void;
  onAdjust: () => void;
  onHear: () => Promise<string>;
}

/** One detected fix: what it found, in plain English, with Hear it / Adjust / on-off. */
export default function FixCard({ fix, index, onToggle, onAdjust, onHear }: FixCardProps) {
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleHear = async () => {
    setLoading(true);
    setError(null);
    try {
      const path = await onHear();
      setPreviewPath(path);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className={`rounded-xl border p-3.5 ${
        fix.enabled ? 'bg-raised border-white/9' : 'bg-raised/60 border-white/6'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-signal/15 border border-signal/30 flex items-center justify-center font-mono text-xs font-semibold text-signal flex-none">
          {String(index + 1).padStart(2, '0')}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-semibold text-sm text-text">{fix.title}</h4>
            {fix.confidence && (
              <span
                className={`font-mono text-[9.5px] tracking-wide px-1.5 py-0.5 rounded ${CONFIDENCE_COLOR[fix.confidence]}`}
              >
                {CONFIDENCE_LABEL[fix.confidence]}
              </span>
            )}
          </div>
          <p className="text-xs text-text/60 mt-1 leading-relaxed">{fix.body}</p>

          {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
          {previewPath && !error && (
            <audio
              controls
              autoPlay
              preload="none"
              src={`/api/produce/clean/preview?path=${encodeURIComponent(previewPath)}`}
              className="h-8 mt-2 w-full max-w-xs"
            />
          )}

          <div className="flex gap-1.5 mt-2.5">
            <button
              onClick={handleHear}
              disabled={loading}
              className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-2.5 py-1 hover:bg-white/5 disabled:opacity-50"
            >
              {loading ? 'Rendering…' : 'Hear it'}
            </button>
            <button
              onClick={onAdjust}
              className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-2.5 py-1 hover:bg-white/5"
            >
              Adjust
            </button>
          </div>
        </div>

        <button
          onClick={onToggle}
          className="flex items-center gap-2 flex-none"
          aria-label={fix.enabled ? 'Turn this fix off' : 'Turn this fix on'}
        >
          <span className={`font-mono text-[10.5px] font-semibold ${fix.enabled ? 'text-confirm' : 'text-text/35'}`}>
            {fix.enabled ? 'ON' : 'OFF'}
          </span>
          <span
            className={`w-[38px] h-[22px] rounded-full relative transition-colors ${
              fix.enabled ? 'bg-confirm' : 'bg-white/13'
            }`}
          >
            <span
              className={`absolute top-0.5 w-[18px] h-[18px] rounded-full transition-all ${
                fix.enabled ? 'right-0.5 bg-canvas' : 'left-0.5 bg-text/55'
              }`}
            />
          </span>
        </button>
      </div>
    </div>
  );
}
