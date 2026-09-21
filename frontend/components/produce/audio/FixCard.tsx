'use client';

import type { FixEntry, ParamMeta } from '@/hooks/useProcessingQueue';
import { CONFIDENCE_COLOR, CONFIDENCE_LABEL } from './stemColors';

interface FixCardProps {
  fix: FixEntry;
  index: number;
  onToggle: () => void;
  onAdjust: () => void;
  /** Audition this fix on the console transport — the page's only player. */
  onHear: () => void;
  /** Only passed for producer-added cards — a measured fix is toggled, not deleted. */
  onRemove?: () => void;
  /** Required params still unset — the card can't run until they have values. */
  missingParams?: ParamMeta[];
  /** This is the card the transport is currently playing. */
  auditioning?: boolean;
  /** Its chain is being rendered before playback can start. */
  rendering?: boolean;
  /** The console has decoded audio — until then there is nothing to play into. */
  canHear?: boolean;
}

/** One fix: what it found, in plain English, with Hear it / Adjust / on-off. */
export default function FixCard({
  fix,
  index,
  onToggle,
  onAdjust,
  onHear,
  onRemove,
  missingParams = [],
  auditioning = false,
  rendering = false,
  canHear = true,
}: FixCardProps) {
  const incomplete = missingParams.length > 0;

  // What the queue will really run: enabled and complete.
  const on = fix.enabled && !incomplete;

  const hearLabel = rendering ? 'Rendering…' : auditioning ? 'Playing' : 'Hear it';
  const hearTitle = incomplete
    ? 'Set the missing setting under Adjust first'
    : !canHear
      ? 'Waiting for the console to load this song’s audio'
      : 'Play this fix in the mix, on the console transport';

  return (
    <div
      className={`rounded-xl border p-3.5 ${
        on ? 'bg-raised border-white/9' : 'bg-raised/60 border-white/6'
      } ${incomplete ? 'border-amber-400/30' : ''} ${
        auditioning ? 'ring-1 ring-signal/50' : ''
      }`}
    >
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-lg bg-signal/15 border border-signal/30 flex items-center justify-center font-mono text-xs font-semibold text-signal flex-none">
          {String(index + 1).padStart(2, '0')}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h4 className="font-semibold text-sm text-text">{fix.title}</h4>
            {fix.source === 'manual' ? (
              <span className="font-mono text-[9.5px] tracking-wide px-1.5 py-0.5 rounded text-signal bg-signal/15">
                ADDED BY YOU
              </span>
            ) : (
              fix.confidence && (
                <span
                  className={`font-mono text-[9.5px] tracking-wide px-1.5 py-0.5 rounded ${CONFIDENCE_COLOR[fix.confidence]}`}
                >
                  {CONFIDENCE_LABEL[fix.confidence]}
                </span>
              )
            )}
            {auditioning && (
              <span className="font-mono text-[9.5px] tracking-wide px-1.5 py-0.5 rounded text-signal bg-signal/15">
                ON THE TRANSPORT
              </span>
            )}
          </div>
          <p className="text-xs text-text/60 mt-1 leading-relaxed">{fix.body}</p>

          {/* An enabled-looking card that would be silently dropped from the
              render is worse than one that says what it is waiting for. */}
          {incomplete && (
            <p className="text-xs text-amber-400/90 mt-1.5">
              Needs {missingParams.map((p) => p.label).join(' and ')} before this runs — set it
              under Adjust.
            </p>
          )}

          <div className="flex gap-1.5 mt-2.5">
            <button
              onClick={onHear}
              disabled={incomplete || !canHear || rendering}
              title={hearTitle}
              className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-2.5 py-1 hover:bg-white/5 disabled:opacity-50"
            >
              {hearLabel}
            </button>
            <button
              onClick={onAdjust}
              className="text-xs font-semibold text-text/70 border border-white/14 rounded-lg px-2.5 py-1 hover:bg-white/5"
            >
              Adjust
            </button>
            {onRemove && (
              <button
                onClick={onRemove}
                className="text-xs font-semibold text-text/50 border border-white/14 rounded-lg px-2.5 py-1 hover:bg-white/5 hover:text-text/80"
              >
                Remove
              </button>
            )}
          </div>
        </div>

        {/* `on` is what the queue will actually render, which is not the same as
            `fix.enabled` while a required setting is still blank. */}
        <button
          onClick={onToggle}
          disabled={incomplete}
          className="flex items-center gap-2 flex-none disabled:cursor-not-allowed"
          aria-label={
            incomplete
              ? 'Set the missing setting under Adjust before turning this on'
              : fix.enabled
                ? 'Turn this fix off'
                : 'Turn this fix on'
          }
        >
          <span className={`font-mono text-[10.5px] font-semibold ${on ? 'text-confirm' : 'text-text/35'}`}>
            {incomplete ? 'SET UP' : on ? 'ON' : 'OFF'}
          </span>
          <span
            className={`w-[38px] h-[22px] rounded-full relative transition-colors ${
              on ? 'bg-confirm' : 'bg-white/13'
            }`}
          >
            <span
              className={`absolute top-0.5 w-[18px] h-[18px] rounded-full transition-all ${
                on ? 'right-0.5 bg-canvas' : 'left-0.5 bg-text/55'
              }`}
            />
          </span>
        </button>
      </div>
    </div>
  );
}
