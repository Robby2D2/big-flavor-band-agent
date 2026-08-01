'use client';

import type { FixEntry } from '@/hooks/useProcessingQueue';

interface ParamMeta {
  name: string;
  type: string;
  default: any;
  min: number | null;
  max: number | null;
  label: string;
  help: string | null;
  choices: any[] | null;
}

interface AdvancedDrawerProps {
  fix: FixEntry;
  paramsMeta: ParamMeta[];
  onChange: (patch: Record<string, any>) => void;
  onReset: () => void;
  onClose: () => void;
}

/** Every parameter a tool declares, pre-filled from analysis, individually tunable. */
export default function AdvancedDrawer({ fix, paramsMeta, onChange, onReset, onClose }: AdvancedDrawerProps) {
  // Only show params analyze actually surfaced a value for (file_path/output_path
  // etc. are plumbing, not something a producer tunes here) — falling back to
  // every declared param when analyze returned none (e.g. correct_beats).
  const relevant = paramsMeta.filter(
    (p) => p.name !== 'file_path' && p.name !== 'output_path' && p.type !== 'array' && p.type !== 'object'
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-sm bg-panel border-l border-white/9 h-full overflow-y-auto flex flex-col">
        <div className="p-4 border-b border-white/8 flex items-start justify-between">
          <div>
            <h3 className="font-semibold text-text">{fix.title}</h3>
            <p className="font-mono text-[11px] text-text/40 mt-1">{fix.tool}</p>
          </div>
          <button onClick={onClose} className="text-text/40 hover:text-text text-lg leading-none">
            ✕
          </button>
        </div>

        <div className="p-4 flex flex-col gap-5 flex-1">
          {relevant.length === 0 && (
            <p className="text-xs text-text/40">This tool has no tunable parameters.</p>
          )}
          {relevant.map((p) => {
            const value = fix.currentParams[p.name] ?? p.default;
            if (p.type === 'boolean') {
              return (
                <label key={p.name} className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-text">{p.label}</div>
                    {p.help && <div className="text-[10.5px] text-text/40 mt-0.5">{p.help}</div>}
                  </div>
                  <input
                    type="checkbox"
                    checked={!!value}
                    onChange={(e) => onChange({ [p.name]: e.target.checked })}
                    className="h-4 w-4"
                  />
                </label>
              );
            }
            if (p.choices && p.choices.length > 0) {
              return (
                <label key={p.name}>
                  <div className="text-sm font-semibold text-text mb-1">{p.label}</div>
                  <select
                    value={value ?? ''}
                    onChange={(e) => onChange({ [p.name]: e.target.value })}
                    className="w-full px-2 py-1.5 bg-well border border-white/10 rounded-lg text-text text-sm"
                  >
                    {p.choices.map((c) => (
                      <option key={String(c)} value={c}>
                        {String(c)}
                      </option>
                    ))}
                  </select>
                </label>
              );
            }
            const hasRange = p.min != null && p.max != null;
            return (
              <div key={p.name}>
                <div className="flex items-baseline justify-between mb-1.5">
                  <div>
                    <div className="text-sm font-semibold text-text">{p.label}</div>
                    {p.help && <div className="text-[10.5px] text-text/40 mt-0.5">{p.help}</div>}
                  </div>
                  <span className="font-mono text-sm font-semibold text-signal bg-signal/10 px-2 py-0.5 rounded">
                    {typeof value === 'number' ? value : value ?? '—'}
                  </span>
                </div>
                {hasRange ? (
                  <input
                    type="range"
                    min={p.min!}
                    max={p.max!}
                    step={(p.max! - p.min!) / 100 || 1}
                    value={typeof value === 'number' ? value : p.default ?? 0}
                    onChange={(e) => onChange({ [p.name]: Number(e.target.value) })}
                    className="w-full"
                  />
                ) : (
                  <input
                    type="number"
                    value={typeof value === 'number' ? value : ''}
                    onChange={(e) => onChange({ [p.name]: Number(e.target.value) })}
                    className="w-full px-2 py-1.5 bg-well border border-white/10 rounded-lg text-text text-sm"
                  />
                )}
              </div>
            );
          })}
        </div>

        <div className="p-4 border-t border-white/8 flex gap-2">
          <button
            onClick={onReset}
            className="flex-1 text-sm font-semibold text-text/65 border border-white/14 rounded-lg py-2.5"
          >
            Reset to suggested
          </button>
          <button
            onClick={onClose}
            className="flex-1 text-sm font-semibold text-canvas bg-signal rounded-lg py-2.5"
          >
            Keep
          </button>
        </div>
      </div>
    </div>
  );
}
