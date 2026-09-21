import type { FixNotice } from '@/hooks/useAcceptJob';

/**
 * What a render has to say about fixes that ran but did less than their card
 * promised — today, a pitch correction that fell back to a whole-file shift.
 *
 * Shown in two places because a render resolves in two: a preview resolves in
 * the sidebar that started it, while a save resolves on the page — by the time
 * it lands, the saved version is selected and the review queue it came from has
 * been cleared. Accepting a fix and getting unchanged audio back with nothing
 * said is the outcome this exists to prevent (issue #91), so it must survive
 * that hand-off.
 */
export default function FixNoticePanel({ notices }: { notices: FixNotice[] }) {
  if (notices.length === 0) return null;

  return (
    <div className="bg-attention/10 border border-attention/30 rounded-xl p-3.5">
      <p className="text-sm text-attention font-semibold">
        {notices.length === 1
          ? 'One fix did less than it said'
          : `${notices.length} fixes did less than they said`}
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {notices.map((n) => (
          <li key={`${n.scope}:${n.tool}`} className="text-xs text-text/60">
            <span className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
              {n.scope}
            </span>
            <span className="block mt-0.5">{n.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
