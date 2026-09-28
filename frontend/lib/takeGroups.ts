/**
 * How a session's takes are laid out for review, once some of them are known to
 * be attempts at the same song.
 *
 * The backend decides *which* takes belong together (it has the transcripts and
 * the human's corrections). This module decides what review shows: one row per
 * song, a row of its own for every take no group claimed, and the name each
 * group is headed by.
 *
 * Two rules it exists to make testable:
 *
 * - **Nothing is lost.** Grouping rearranges takes, it never removes them, so
 *   the rows must flatten back to exactly the takes that went in (SESS-14).
 * - **A group's name is still a generated name.** It is guessed from the takes'
 *   own words through `takeName`, not written here, so the six-word cap and the
 *   wordless label are inherited rather than re-implemented (SESS-12).
 */
import { TakeName, takeName } from '@/lib/takeName';

/** The fields of a take this module needs. */
export interface GroupableTake {
  id: number;
  group_id: number | null;
  start_seconds: number;
  transcript: string | null;
}

export interface TakeGroupRecord {
  id: number;
  /** The name a producer set by hand, or null to show the guess. */
  name: string | null;
  keeper_take_id: number | null;
}

/** A take plus its 1-based position in the session, which never changes. */
export interface PositionedTake<T extends GroupableTake> {
  take: T;
  /** Position among *all* the session's takes — a take's stable handle. */
  position: number;
}

export interface GroupRow<T extends GroupableTake> {
  kind: 'group';
  group: TakeGroupRecord;
  takes: PositionedTake<T>[];
}

export interface LoneRow<T extends GroupableTake> {
  kind: 'take';
  take: T;
  position: number;
}

export type ReviewRow<T extends GroupableTake> = GroupRow<T> | LoneRow<T>;

/** A group's headline, and whether the producer wrote it. */
export interface GroupName extends TakeName {
  /** A human named this group, so it is not a guess any more. */
  chosen: boolean;
}

/**
 * Lay a session's takes out for review.
 *
 * Takes arrive in timeline order and keep it: a group sits where its first take
 * sits, so the page still reads as the night did. A group referenced by no take
 * (every member was separated out) produces no row — its takes are all still
 * there, on their own.
 */
export function reviewRows<T extends GroupableTake>(
  takes: T[],
  groups: TakeGroupRecord[]
): ReviewRow<T>[] {
  const byId = new Map(groups.map((group) => [group.id, group]));
  const rows: ReviewRow<T>[] = [];
  const groupRows = new Map<number, GroupRow<T>>();

  takes.forEach((take, index) => {
    const position = index + 1;
    const group = take.group_id === null ? undefined : byId.get(take.group_id);

    // A group_id pointing at a group the payload does not carry would silently
    // drop the take, so it falls back to standing on its own.
    if (!group) {
      rows.push({ kind: 'take', take, position });
      return;
    }

    const existing = groupRows.get(group.id);
    if (existing) {
      existing.takes.push({ take, position });
      return;
    }

    const row: GroupRow<T> = { kind: 'group', group, takes: [{ take, position }] };
    groupRows.set(group.id, row);
    rows.push(row);
  });

  return rows;
}

/** Every take the rows hold, however they are arranged. */
export function rowTakes<T extends GroupableTake>(rows: ReviewRow<T>[]): T[] {
  return rows.flatMap((row) =>
    row.kind === 'group' ? row.takes.map((member) => member.take) : [row.take]
  );
}

/**
 * What a group of takes is called.
 *
 * The guess comes from the take with the **most** words, because that is the
 * fullest attempt at the song and the least likely to be a false start that
 * stopped after a line. A producer's own name always wins, and a group whose
 * takes sang nothing is labelled as wordless rather than titled.
 */
export function groupName<T extends GroupableTake>(
  group: TakeGroupRecord,
  takes: PositionedTake<T>[]
): GroupName {
  const chosen = (group.name ?? '').trim();
  if (chosen) {
    return { text: chosen, shortened: false, wordless: false, chosen: true };
  }

  const fullest = takes.reduce<string>((best, member) => {
    const transcript = member.take.transcript ?? '';
    return transcript.length > best.length ? transcript : best;
  }, '');

  return { ...takeName(fullest), chosen: false };
}
