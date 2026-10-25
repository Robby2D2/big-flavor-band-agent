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
  /** The catalog song this group was produced into, or null while staged. */
  song_id: number | null;
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

/** The takes a take can be joined with: right before and after it (SESS-23). */
export interface TakeNeighbours<T extends GroupableTake> {
  before: PositionedTake<T> | null;
  after: PositionedTake<T> | null;
}

/**
 * Each take's timeline neighbours within its own recording pass.
 *
 * A pass is its own timeline — a room-recorded night has one per file — so the
 * last take of one pass and the first of the next are not neighbours. Takes
 * arrive in timeline order, and positions match `reviewRows`.
 */
export function takeNeighbours<T extends GroupableTake & { rec_pass: number | null }>(
  takes: T[]
): Map<number, TakeNeighbours<T>> {
  const result = new Map<number, TakeNeighbours<T>>();
  const lastInPass = new Map<number | null, PositionedTake<T>>();

  takes.forEach((take, index) => {
    const current = { take, position: index + 1 };
    const before = lastInPass.get(take.rec_pass) ?? null;
    result.set(take.id, { before, after: null });
    const previous = before ? result.get(before.take.id) : undefined;
    if (previous) previous.after = current;
    lastInPass.set(take.rec_pass, current);
  });

  return result;
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
 * The guess comes from the take with the **longest** transcript, because that is
 * the fullest attempt at the song and the least likely to be a false start that
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
