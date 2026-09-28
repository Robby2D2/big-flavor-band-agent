'use client';

import { useState } from 'react';

import TakeCard, { SessionTake } from '@/components/produce/session/TakeCard';
import {
  PositionedTake,
  TakeGroupRecord,
  groupName,
} from '@/lib/takeGroups';

interface TakeGroupCardProps {
  group: TakeGroupRecord;
  takes: PositionedTake<SessionTake>[];
  onRename: (group: TakeGroupRecord, name: string) => void;
  onChooseKeeper: (group: TakeGroupRecord, take: SessionTake) => void;
  onSeparate: (take: SessionTake) => void;
  onToggleExcluded: (take: SessionTake) => void;
}

/**
 * The several attempts the band made at one song, as one card.
 *
 * Two things it must keep saying out loud. The name and the grouping are a
 * **guess** drawn from the words, not a catalog match (SESS-05) — so the card
 * offers to be corrected rather than presenting itself as settled. And no keeper
 * is chosen until the producer chooses one (SESS-15), which is the only thing
 * that could ever make a take eligible to leave staging.
 */
export default function TakeGroupCard({
  group,
  takes,
  onRename,
  onChooseKeeper,
  onSeparate,
  onToggleExcluded,
}: TakeGroupCardProps) {
  const name = groupName(group, takes);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name.text);

  const startEditing = () => {
    setDraft(name.chosen ? name.text : '');
    setEditing(true);
  };

  const commit = () => {
    setEditing(false);
    const next = draft.trim();
    if (next !== (group.name ?? '').trim()) onRename(group, next);
  };

  const keeper = takes.find((member) => member.take.id === group.keeper_take_id);

  return (
    <li className="rounded border border-signal/30 bg-panel">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-raised p-4">
        {editing ? (
          <input
            autoFocus
            value={draft}
            placeholder={name.text}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === 'Enter') commit();
              if (event.key === 'Escape') setEditing(false);
            }}
            className="flex-1 rounded border border-raised bg-well px-2 py-1 text-sm"
          />
        ) : (
          <button
            type="button"
            onClick={startEditing}
            className="flex-1 text-left"
            title="Rename this song"
          >
            <span
              className={`text-base font-medium ${
                name.wordless ? 'italic text-text/60' : ''
              }`}
            >
              {name.text}
              {name.shortened && <span className="text-text/40">…</span>}
            </span>
            {!name.chosen && (
              <span className="ml-2 text-xs text-text/40">
                guessed — click to rename
              </span>
            )}
          </button>
        )}

        <span className="text-sm text-text/60">
          {takes.length} {takes.length === 1 ? 'take' : 'takes'}
        </span>
      </div>

      <ul className="divide-y divide-raised">
        {takes.map((member) => (
          <TakeCard
            key={member.take.id}
            take={member.take}
            index={member.position}
            inGroup
            isKeeper={member.take.id === group.keeper_take_id}
            onChooseKeeper={(take) => onChooseKeeper(group, take)}
            onSeparate={onSeparate}
            onToggleExcluded={onToggleExcluded}
          />
        ))}
      </ul>

      <p className="px-4 py-3 text-xs text-text/40">
        {keeper
          ? `Take ${keeper.position} is the keeper.`
          : 'No keeper chosen. Nothing from this song reaches the catalog until you pick one.'}{' '}
        These takes were grouped by the words they share, which is a guess — separate
        any take that is a different song.
      </p>
    </li>
  );
}
