'use client';

export type MeterTone = 'ok' | 'warning' | 'critical';

const TONE_FILL: Record<MeterTone, string> = {
  ok: 'bg-blue-500 dark:bg-blue-400',
  warning: 'bg-amber-500 dark:bg-amber-400',
  critical: 'bg-red-500 dark:bg-red-400',
};

interface MeterProps {
  /** Direct-labeled value shown beside the track, e.g. "-26.3 dB". */
  valueLabel: string;
  /** Current value's position on the track, 0..1. */
  fraction: number;
  /** Optional target position on the same scale, 0..1. */
  target?: number;
  tone: MeterTone;
}

/** A single-value gauge against a fixed scale, with an optional target tick. */
export function Meter({ valueLabel, fraction, target, tone }: MeterProps) {
  const pct = Math.round(Math.min(1, Math.max(0, fraction)) * 100);
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="relative flex-1 h-2 max-w-xs rounded-full bg-gray-200 dark:bg-gray-700">
        <div
          className={`absolute inset-y-0 left-0 rounded-full ${TONE_FILL[tone]}`}
          style={{ width: `${pct}%` }}
        />
        {target != null && (
          <div
            className="absolute inset-y-0 w-px bg-gray-500 dark:bg-gray-300"
            style={{ left: `${Math.round(Math.min(1, Math.max(0, target)) * 100)}%` }}
            title="Target"
          />
        )}
      </div>
      <span className="text-xs text-gray-500 dark:text-gray-400 tabular-nums whitespace-nowrap">
        {valueLabel}
      </span>
    </div>
  );
}

interface BalanceBarProps {
  bass: number;
  mid: number;
  treble: number;
}

const BAND_COLOR = {
  bass: 'bg-blue-500 dark:bg-blue-400',
  mid: 'bg-teal-500 dark:bg-teal-400',
  treble: 'bg-amber-500 dark:bg-amber-400',
};

/** A 3-segment share bar for the bass/mid/treble frequency balance. */
export function BalanceBar({ bass, mid, treble }: BalanceBarProps) {
  const bands: { key: keyof typeof BAND_COLOR; label: string; pct: number }[] = [
    { key: 'bass', label: 'Bass', pct: bass },
    { key: 'mid', label: 'Mid', pct: mid },
    { key: 'treble', label: 'Treble', pct: treble },
  ];
  return (
    <div className="mt-1 max-w-xs">
      <div className="flex h-3 gap-0.5 rounded-full overflow-hidden bg-gray-100 dark:bg-gray-800">
        {bands.map((b) => (
          <div
            key={b.key}
            className={`h-full ${BAND_COLOR[b.key]} flex items-center justify-center`}
            style={{ width: `${Math.max(0, b.pct)}%` }}
            title={`${b.label}: ${b.pct.toFixed(0)}%`}
          >
            {b.pct >= 12 && (
              <span className="text-[10px] font-medium text-white px-0.5">
                {Math.round(b.pct)}%
              </span>
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-3 mt-1 text-[10px] text-gray-500 dark:text-gray-400">
        {bands.map((b) => (
          <span key={b.key} className="flex items-center gap-1">
            <span className={`inline-block w-2 h-2 rounded-sm ${BAND_COLOR[b.key]}`} />
            {b.label} {b.pct.toFixed(0)}%
          </span>
        ))}
      </div>
    </div>
  );
}
