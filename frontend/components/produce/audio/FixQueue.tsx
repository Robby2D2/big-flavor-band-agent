'use client';

import type { FixEntry, ParamMeta, ToolInfo } from '@/hooks/useProcessingQueue';
import FixCard from './FixCard';
import { fixTitleFor } from './fixCopy';

interface FixQueueProps {
  /** The open row's fixes — on the full-mix row, the master fixes. */
  fixes: FixEntry[];
  analyzing?: boolean;
  /** Tools the producer can still add to this row. */
  addableTools: ToolInfo[];
  onToggle: (id: string) => void;
  onAdjust: (fix: FixEntry) => void;
  onAddFix: (tool: string) => void;
  onRemoveFix: (id: string) => void;
  /** Required params a card still has no value for, by fix id. */
  missingParamsFor: (fix: FixEntry) => ParamMeta[];
}

/**
 * One console row's review queue, shown beneath the row when it is opened.
 * The full-mix row's queue is the whole-song bucket — trim, tone balance and
 * loudness are reviewed once per song, not once per stem — so it is reached
 * the same way as any stem's, and is not repeated under every other row.
 *
 * The analysis is where the queue starts, not where it ends: the picker under
 * the cards adds a fix the measurements never flagged, which then behaves like
 * any other card.
 */
export default function FixQueue({
  fixes,
  analyzing = false,
  addableTools,
  onToggle,
  onAdjust,
  onAddFix,
  onRemoveFix,
  missingParamsFor,
}: FixQueueProps) {
  return (
    <div className={`flex flex-col gap-3 transition-opacity ${analyzing ? 'opacity-40 pointer-events-none select-none' : ''}`}>
      <div className="flex flex-col gap-2.5">
        {fixes.length === 0 ? (
          <p className="text-sm text-text/40">
            {analyzing ? 'Analyzing…' : 'Nothing detected here — add a fix below if you hear one.'}
          </p>
        ) : (
          fixes.map((fix, i) => (
            <FixCard
              key={fix.id}
              fix={fix}
              index={i}
              onToggle={() => onToggle(fix.id)}
              onAdjust={() => onAdjust(fix)}
              onRemove={fix.source === 'manual' ? () => onRemoveFix(fix.id) : undefined}
              missingParams={missingParamsFor(fix)}
            />
          ))
        )}
      </div>

      {/* Hidden when there is nothing left to offer — every tool for this row
          is already queued, or the tool list hasn't loaded yet. */}
      {addableTools.length > 0 && (
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
    </div>
  );
}
