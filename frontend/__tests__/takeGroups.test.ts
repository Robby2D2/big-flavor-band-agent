/**
 * How a session's takes are laid out for review once some are grouped (issue #109).
 *
 * The two cases that matter are the two promises: no take may vanish into a group
 * (SESS-14), and a group's name is still a *generated* name — guessed from the
 * takes' own words, six words at most, and never invented for takes that sang
 * nothing (SESS-12).
 */
import { describe, it, expect } from 'vitest';

import { MAX_NAME_WORDS, WORDLESS_NAME } from '@/lib/takeName';
import {
  GroupableTake,
  TakeGroupRecord,
  groupName,
  reviewRows,
  rowTakes,
} from '@/lib/takeGroups';

const SO_TIRED =
  'so tired of waiting for the morning light to fall across the kitchen floor';

const take = (
  id: number,
  group_id: number | null,
  start_seconds: number,
  transcript: string | null = SO_TIRED
): GroupableTake => ({ id, group_id, start_seconds, transcript });

const group = (
  id: number,
  name: string | null = null,
  keeper_take_id: number | null = null
): TakeGroupRecord => ({ id, name, keeper_take_id });

describe('reviewRows', () => {
  it('puts the takes of one song in a single row', () => {
    const rows = reviewRows(
      [take(8, 1, 2760), take(9, 1, 3040)],
      [group(1)]
    );

    expect(rows).toHaveLength(1);
    expect(rows[0].kind).toBe('group');
    expect(rows[0].kind === 'group' && rows[0].takes.map((m) => m.take.id)).toEqual([
      8, 9,
    ]);
  });

  it('shows an ungrouped take on its own', () => {
    // Take 7 transitions between songs, so it belongs to neither.
    const rows = reviewRows(
      [take(7, null, 2400), take(8, 1, 2760), take(9, 1, 3040)],
      [group(1)]
    );

    expect(rows.map((row) => row.kind)).toEqual(['take', 'group']);
  });

  it('never loses or duplicates a take', () => {
    const takes = [
      take(1, null, 0),
      take(2, 1, 100),
      take(3, 2, 200),
      take(4, 1, 300),
      take(5, null, 400),
      take(6, 2, 500),
    ];

    const rows = reviewRows(takes, [group(1), group(2)]);

    expect(rowTakes(rows).map((row) => row.id).sort()).toEqual([1, 2, 3, 4, 5, 6]);
    expect(rowTakes(rows)).toHaveLength(takes.length);
  });

  it('keeps every take\'s position in the session, group or not', () => {
    const rows = reviewRows(
      [take(7, null, 2400), take(8, 1, 2760), take(9, 1, 3040)],
      [group(1)]
    );

    const positions = rows.flatMap((row) =>
      row.kind === 'group' ? row.takes.map((m) => m.position) : [row.position]
    );
    expect(positions).toEqual([1, 2, 3]);
  });

  it('shows a take on its own when its group is missing from the payload', () => {
    // A dangling group_id must never be a reason a take disappears.
    const rows = reviewRows([take(4, 99, 10)], []);

    expect(rows).toEqual([{ kind: 'take', take: take(4, 99, 10), position: 1 }]);
  });

  it('orders a group where its first take falls in the session', () => {
    const rows = reviewRows(
      [take(1, 1, 0), take(2, null, 100), take(3, 1, 200)],
      [group(1)]
    );

    expect(rows[0].kind).toBe('group');
    expect(rows[1].kind === 'take' && rows[1].take.id).toBe(2);
  });
});

describe('groupName', () => {
  const positioned = (takes: GroupableTake[]) =>
    takes.map((take, index) => ({ take, position: index + 1 }));

  it('guesses from the fullest take and obeys the six-word cap', () => {
    const name = groupName(
      group(1),
      positioned([take(1, 1, 0, 'so tired of waiting'), take(2, 1, 100, SO_TIRED)])
    );

    expect(name.text).toBe('so tired of waiting for the');
    expect(name.text.split(/\s+/)).toHaveLength(MAX_NAME_WORDS);
    expect(name.shortened).toBe(true);
    expect(name.chosen).toBe(false);
  });

  it('labels a group whose takes sang nothing rather than titling it', () => {
    const name = groupName(
      group(1),
      positioned([take(1, 1, 0, null), take(2, 1, 100, '')])
    );

    expect(name.text).toBe(WORDLESS_NAME);
    expect(name.wordless).toBe(true);
    expect(name.chosen).toBe(false);
  });

  it('prefers the name a producer set', () => {
    const name = groupName(group(1, 'So Tired'), positioned([take(1, 1, 0)]));

    expect(name.text).toBe('So Tired');
    expect(name.chosen).toBe(true);
    expect(name.shortened).toBe(false);
  });

  it('treats a blank producer name as no name at all', () => {
    const name = groupName(group(1, '   '), positioned([take(1, 1, 0, SO_TIRED)]));

    expect(name.chosen).toBe(false);
    expect(name.text).toBe('so tired of waiting for the');
  });
});
