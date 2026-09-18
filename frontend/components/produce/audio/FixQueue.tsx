'use client';

import type { FixEntry, ToolInfo } from '@/hooks/useProcessingQueue';
import FixCard from './FixCard';
import { fixTitleFor } from './fixCopy';

interface FixQueueProps {
  stemName: string | null;
  /** Badge for the selected row's scope — "THIS STEM", or "FULL MIX". */
  scopeLabel?: string;
  stemFixes: FixEntry[];
  masterFixes: FixEntry[];
  analyzing?: boolean;
  /** Tools the producer can still add to the selected row. */
  addableTools: ToolInfo[];
  onToggle: (id: string) => void;
  onAdjust: (fix: FixEntry) => void;
  onHear: (fix: FixEntry) => Promise<string>;
  onAddFix: (tool: string) => void;
  onRemoveFix: (id: string) => void;
}

/**
 * The review queue for the selected stem, plus the whole-mix/master bucket
 * underneath — trim, tone balance, and loudness are reviewed once per song,
 * not once per stem.
 *
 * The analysis is where the queue starts, not where it ends: the picker under
 * the selected row's cards adds a fix the measurements never flagged, which
 * then behaves like any other card.
 */
export default function FixQueue({
  stemName,
  scopeLabel = 'THIS STEM',
  stemFixes,
  masterFixes,
  analyzing = false,
  addableTools,
  onToggle,
  onAdjust,
  onHear,
  onAddFix,
  onRemoveFix,
}: FixQueueProps) {
  return (
    <div className={`flex flex-col gap-4 transition-opacity ${analyzing ? 'opacity-40 pointer-events-none select-none' : ''}`}>
      <div>
        <div className="flex items-center gap-2">
          <h3 className="font-semibold text-text">
            {stemName ? (
              <>
                <span className="capitalize">{stemName}</span> — {stemFixes.length} fix
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
            {analyzing ? 'Analyzing…' : 'Nothing detected for this stem — add a fix below if you hear one.'}
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
              onRemove={fix.source === 'manual' ? () => onRemoveFix(fix.id) : undefined}
            />
          ))
        )}
      </div>

      {/* Hidden when there is nothing left to offer — every tool for this row
          is already queued, or the tool list hasn't loaded yet. */}
      {stemName && addableTools.length > 0 && (
        <div className="flex items-center gap-2">
          <label htmlFor="add-fix" className="text-xs text-text/45">
            Heard something the analysis missed?
          </label>
          <select
            id="add-fix"
            // Always reads "Add a fix…": picking a tool adds a card rather than
            // selecting a value, so there is nothing for it to stay set to.
            value=""
            onChange={(e) => {
              if (e.target.value) onAddFix(e.target.value);
            }}
            className="px-2 py-1.5 bg-well border border-white/10 rounded-lg text-text text-xs"
          >
            <option value="">Add a fix…</option>
            {/* Listed by the title the card will carry, not the tool's own
                summary, so picking "Even out the tone" doesn't produce a card
                called something else. The summary is the hover text. */}
            {addableTools.map((tool) => (
              <option key={tool.name} value={tool.name} title={tool.summary}>
                {fixTitleFor(tool.name, tool.summary)}
              </option>
            ))}
          </select>
        </div>
      )}

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
                onRemove={fix.source === 'manual' ? () => onRemoveFix(fix.id) : undefined}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
