'use client';

import { useState } from 'react';

import TakeCard, {
  MoveTarget,
  SessionTake,
  SongOption,
} from '@/components/produce/session/TakeCard';
import {
  PositionedTake,
  TakeGroupRecord,
  groupName,
} from '@/lib/takeGroups';

interface TakeGroupCardProps {
  group: TakeGroupRecord;
  takes: PositionedTake<SessionTake>[];
  songs: SongOption[];
  /** A produce request for this group is in flight. */
  producing: boolean;
  onRename: (group: TakeGroupRecord, name: string) => void;
  onProduce: (group: TakeGroupRecord, title: string) => void;
  onMove: (take: SessionTake, target: MoveTarget) => void;
  onToggleExcluded: (take: SessionTake) => void;
}

/**
 * The several attempts the band made at one song, as one card.
 *
 * The name and the grouping are a **guess** drawn from the words, not a catalog
 * match (SESS-05) — so the card offers to be corrected rather than presenting
 * itself as settled. Nothing leaves review until the producer presses Produce,
 * which brings the takes into the catalog as one song's versions (SESS-19);
 * which of them is the default is chosen on the produce page (SESS-15).
 */
export default function TakeGroupCard({
  group,
  takes,
  songs,
  producing,
  onRename,
  onProduce,
  onMove,
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

  const produced = group.song_id !== null;
  const waiting = takes.filter(
    (member) =>
      member.take.song_version_id === null &&
      !member.take.excluded &&
      member.take.has_audio
  ).length;
  const canProduce = produced || waiting > 0;

  return (
    <li className="rounded border border-signal/30 bg-panel">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-raised p-4">
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
            className="min-w-0 flex-1 rounded border border-raised bg-well px-2 py-1 text-sm"
          />
        ) : (
          <button
            type="button"
            onClick={startEditing}
            className="min-w-0 flex-1 text-left"
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

        <button
          type="button"
          onClick={() => onProduce(group, name.text)}
          disabled={!canProduce || producing}
          title={
            canProduce
              ? undefined
              : 'Every take here is discarded or has no audio'
          }
          className="rounded bg-signal px-3 py-1.5 text-sm font-medium text-canvas hover:bg-signal/90 disabled:opacity-50"
        >
          {producing
            ? 'Bringing in…'
            : produced && waiting === 0
              ? 'Open in producer →'
              : 'Produce this song →'}
        </button>
      </div>

      <ul className="divide-y divide-raised">
        {takes.map((member) => (
          <TakeCard
            key={member.take.id}
            take={member.take}
            index={member.position}
            inGroup
            songs={songs}
            onMove={onMove}
            onToggleExcluded={onToggleExcluded}
          />
        ))}
      </ul>

      <p className="px-4 py-3 text-xs text-text/40">
        {produced
          ? waiting > 0
            ? `In the catalog. ${waiting} ${
                waiting === 1 ? 'take has' : 'takes have'
              } joined since — producing again adds ${
                waiting === 1 ? 'it' : 'them'
              } as ${waiting === 1 ? 'a version' : 'versions'}.`
            : 'In the catalog. Choose its default version in the producer.'
          : 'Put every take of this song here, then produce it: each take becomes a version, and you choose the default on the next page.'}{' '}
        These takes were grouped by the words they share, which is a guess — move
        any take that is a different song.
      </p>
    </li>
  );
}
