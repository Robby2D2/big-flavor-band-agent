/**
 * Reading the reason out of a backend error body (issue #102).
 *
 * The backend's centralized handlers answer with `{"error": {"code", "message"}}`, not
 * FastAPI's default `{"detail": ...}` — so every BFF route that read `detail` was
 * discarding the wording and showing "Backend API error: Forbidden" instead. That is
 * invisible until a refusal has something worth saying, which is what "you can only
 * remove songs you added yourself" is (RAD-09).
 */
import { describe, expect, it } from 'vitest';
import { backendErrorMessage } from '@/lib/backend';

describe('backendErrorMessage', () => {
  it('reads the shape the backend actually sends', () => {
    expect(
      backendErrorMessage({
        error: { code: 'forbidden', message: 'You can only remove songs you added yourself' },
      })
    ).toBe('You can only remove songs you added yourself');
  });

  it('still reads FastAPI default detail, for responses that bypass those handlers', () => {
    expect(backendErrorMessage({ detail: 'Insufficient role' })).toBe('Insufficient role');
  });

  it('prefers the wrapped message when both are present', () => {
    expect(
      backendErrorMessage({ error: { message: 'wrapped' }, detail: 'raw' })
    ).toBe('wrapped');
  });

  it('returns null when there is nothing to show', () => {
    expect(backendErrorMessage(null)).toBeNull();
    expect(backendErrorMessage(undefined)).toBeNull();
    expect(backendErrorMessage('not an object')).toBeNull();
    expect(backendErrorMessage({})).toBeNull();
    expect(backendErrorMessage({ error: {} })).toBeNull();
    expect(backendErrorMessage({ error: { message: '   ' } })).toBeNull();
    expect(backendErrorMessage({ detail: { loc: ['body'] } })).toBeNull();
  });
});
