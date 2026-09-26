/**
 * Which radio controls a signed-in user is offered (issue #102).
 *
 * The radio page used to hardcode every session's role to 'listener', so `isEditor`
 * could never be true and every queue control was unreachable — for editors too. The
 * regression to keep out is not "a wrong boolean" but a *constant* one, so these tests
 * check that each role and each ownership case reaches a different answer.
 */
import { describe, expect, it } from 'vitest';
import { canRemoveQueueEntry, isEditorRole, queueActionError } from '@/lib/radioControls';

describe('isEditorRole', () => {
  it('admits editor and admin', () => {
    expect(isEditorRole('editor')).toBe(true);
    expect(isEditorRole('admin')).toBe(true);
  });

  it('refuses a listener', () => {
    expect(isEditorRole('listener')).toBe(false);
  });

  it('refuses a role that could not be read', () => {
    // Fail closed for display too: no role means no editor controls (ACCT-04).
    expect(isEditorRole(undefined)).toBe(false);
    expect(isEditorRole(null)).toBe(false);
    expect(isEditorRole('')).toBe(false);
    expect(isEditorRole('wizard')).toBe(false);
  });
});

describe('canRemoveQueueEntry', () => {
  it('offers an editor Remove on any queued song', () => {
    expect(canRemoveQueueEntry({ added_by_me: false }, 'editor')).toBe(true);
    expect(canRemoveQueueEntry({}, 'editor')).toBe(true);
    expect(canRemoveQueueEntry({}, 'admin')).toBe(true);
  });

  it('offers a listener Remove on their own addition', () => {
    expect(canRemoveQueueEntry({ added_by_me: true }, 'listener')).toBe(true);
  });

  it('does not offer a listener Remove on somebody elses addition', () => {
    expect(canRemoveQueueEntry({ added_by_me: false }, 'listener')).toBe(false);
  });

  it('does not offer a listener Remove on a song with no recorded adder', () => {
    // Songs queued before attribution existed, topped up automatically, or asked for
    // through the DJ: nobody owns them, so they are editor-only (RAD-13).
    expect(canRemoveQueueEntry({}, 'listener')).toBe(false);
    expect(canRemoveQueueEntry(undefined, 'listener')).toBe(false);
    expect(canRemoveQueueEntry(null, 'listener')).toBe(false);
  });

  it('distinguishes the roles rather than answering the same way for all of them', () => {
    const someoneElses = { added_by_me: false };
    expect(canRemoveQueueEntry(someoneElses, 'listener')).toBe(false);
    expect(canRemoveQueueEntry(someoneElses, 'editor')).toBe(true);
  });
});

describe('queueActionError', () => {
  it('prefers the reason the server gave', () => {
    expect(
      queueActionError(403, { error: 'You can only remove songs you added yourself' }, 'fallback')
    ).toBe('You can only remove songs you added yourself');
  });

  it('ignores an empty or non-string reason', () => {
    expect(queueActionError(500, { error: '  ' }, 'fallback')).toBe('fallback');
    expect(queueActionError(500, { error: 42 }, 'fallback')).toBe('fallback');
    expect(queueActionError(500, null, 'fallback')).toBe('fallback');
    expect(queueActionError(500, undefined, 'fallback')).toBe('fallback');
  });

  it('explains an expired session and a refusal without a body', () => {
    expect(queueActionError(401, {}, 'fallback')).toMatch(/sign in again/i);
    expect(queueActionError(403, {}, 'fallback')).toMatch(/permission/i);
  });

  it('always returns something to show, never an empty string', () => {
    // RAD-09: a failed action has to say so. Silence is the bug.
    for (const status of [400, 401, 403, 404, 500, 503]) {
      expect(queueActionError(status, null, 'fallback').length).toBeGreaterThan(0);
    }
  });
});
