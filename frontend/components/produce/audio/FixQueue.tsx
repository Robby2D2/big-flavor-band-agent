'use client';

import type { FixEntry } from '@/hooks/useProcessingQueue';
import FixCard from './FixCard';

interface FixQueueProps {
  stemName: string | null;
  /** Badge for the selected row's scope — "THIS STEM", or "FULL MIX". */
  scopeLabel?: string;
  stemFixes: FixEntry[];
  masterFixes: FixEntry[];
  analyzing?: boolean;
  onToggle: (id: string) => void;
  onAdjust: (fix: FixEntry) => void;
  onHear: (fix: FixEntry) => Promise<string>;
}

/**
 * The review queue for the selected stem, plus the whole-mix/master bucket
 * underneath — trim, tone balance, and loudness are reviewed once per song,
 * not once per stem.
 */
export default function FixQueue({
  stemName,
  scopeLabel = 'THIS STEM',
  stemFixes,
  masterFixes,
  analyzing = false,
  onToggle,
  onAdjust,
  onHear,
}: FixQueueProps) {
  return (
    <div className={`flex flex-col gap-4 transition-opacity ${analyzing ? 'opacity-40 pointer-events-none select-none' : ''}`}>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-text">
            {stemName ? (
              <>
                <span className="capitalize">{stemName}</span> — {stemFixes.length} recommended fix
                {stemFixes.length === 1 ? '' : 'es'}
              </>
            ) : (
              'No stem selected'
            )}
          </h3>
          <span className="font-mono text-[9.5px] tracking-wide text-text/45 bg-white/6 px-1.5 py-0.5 rounded">
            {scopeLabel}
          </span>
        </div>
        <p className="text-xs text-text/45 mt-1">
          Pick another row above to tune its chain · master fixes live at the bottom of the list
        </p>
      </div>

      <div className="flex flex-col gap-2.5">
        {stemFixes.length === 0 ? (
          <p className="text-sm text-text/40">
            {analyzing ? 'Analyzing…' : 'Nothing detected for this stem.'}
          </p>
        ) : (
          stemFixes.map((fix, i) => (
            <FixCard
              key={fix.id}
              fix={fix}
              index={i}
              onToggle={() => onToggle(fix.id)}
              onAdjust={() => onAdjust(fix)}
              onHear={() => onHear(fix)}
            />
          ))
        )}
      </div>

      {masterFixes.length > 0 && (
        <div className="pt-3 border-t border-white/8">
          <div className="flex items-center gap-2 mb-2.5">
            <h4 className="font-semibold text-sm text-text">Full mix &amp; master</h4>
            <span className="font-mono text-[9.5px] tracking-wide text-text/45 bg-white/6 px-1.5 py-0.5 rounded">
              MASTER
            </span>
          </div>
          <div className="flex flex-col gap-2.5">
            {masterFixes.map((fix, i) => (
              <FixCard
                key={fix.id}
                fix={fix}
                index={i}
                onToggle={() => onToggle(fix.id)}
                onAdjust={() => onAdjust(fix)}
                onHear={() => onHear(fix)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
