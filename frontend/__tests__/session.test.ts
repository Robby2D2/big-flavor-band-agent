import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createSessionValue, readSessionValue, sessionCookieHeader } from '@/lib/session';

const SECRET = 'test-session-secret';
const USER = {
  sub: '113660068934191103986',
  email: 'friend@example.com',
  name: 'A Friend',
  picture: 'https://example.com/avatar.png',
};

const NOW = Date.UTC(2026, 8, 15, 12, 0, 0);

beforeEach(() => {
  process.env.SESSION_SECRET = SECRET;
});

afterEach(() => {
  process.env.SESSION_SECRET = SECRET;
});

describe('session round trip', () => {
  it('reads back the user it signed', () => {
    expect(readSessionValue(createSessionValue(USER, NOW), NOW)).toEqual(USER);
  });

  it('survives a user with no picture', () => {
    const user = { sub: 'u1', email: 'a@b.com', name: 'A' };
    expect(readSessionValue(createSessionValue(user, NOW), NOW)).toMatchObject(user);
  });
});

describe('forged and damaged cookies are refused', () => {
  it('rejects the old unsigned JSON cookie format', () => {
    // The actual vulnerability: this is exactly what the app used to accept,
    // and anyone could write it by hand with any sub they liked.
    const forged = encodeURIComponent(JSON.stringify({ ...USER, sub: 'an-admins-id' }));
    expect(readSessionValue(forged, NOW)).toBeNull();
  });

  it('rejects a payload edited after signing', () => {
    const signed = createSessionValue(USER, NOW);
    const [, signature] = signed.split('.');
    const tampered = Buffer.from(
      JSON.stringify({ ...USER, sub: 'an-admins-id', exp: 4102444800 }),
      'utf8'
    ).toString('base64url');

    expect(readSessionValue(`${tampered}.${signature}`, NOW)).toBeNull();
  });

  it('rejects a tampered signature', () => {
    const [payload] = createSessionValue(USER, NOW).split('.');
    expect(readSessionValue(`${payload}.not-a-real-signature`, NOW)).toBeNull();
  });

  it('rejects a cookie with no signature at all', () => {
    const [payload] = createSessionValue(USER, NOW).split('.');
    expect(readSessionValue(payload, NOW)).toBeNull();
  });

  it('rejects a session signed with a different secret', () => {
    const signed = createSessionValue(USER, NOW);
    process.env.SESSION_SECRET = 'a-different-secret';
    expect(readSessionValue(signed, NOW)).toBeNull();
  });

  it('rejects empty and undefined values', () => {
    expect(readSessionValue(undefined, NOW)).toBeNull();
    expect(readSessionValue('', NOW)).toBeNull();
  });
});

describe('expiry', () => {
  it('accepts a session inside its window', () => {
    const signed = createSessionValue(USER, NOW);
    const sixDaysLater = NOW + 6 * 24 * 60 * 60 * 1000;
    expect(readSessionValue(signed, sixDaysLater)).toEqual(USER);
  });

  it('rejects a session past its own exp, however it is replayed', () => {
    const signed = createSessionValue(USER, NOW);
    const eightDaysLater = NOW + 8 * 24 * 60 * 60 * 1000;
    expect(readSessionValue(signed, eightDaysLater)).toBeNull();
  });
});

describe('without SESSION_SECRET it fails closed', () => {
  it('refuses to read any session', () => {
    const signed = createSessionValue(USER, NOW);
    delete process.env.SESSION_SECRET;
    expect(readSessionValue(signed, NOW)).toBeNull();
  });

  it('refuses to mint one', () => {
    delete process.env.SESSION_SECRET;
    expect(() => createSessionValue(USER, NOW)).toThrow(/SESSION_SECRET/);
  });
});

describe('cookie header', () => {
  it('is HttpOnly and Lax, and Secure only over https', () => {
    expect(sessionCookieHeader(USER, false)).toContain('HttpOnly');
    expect(sessionCookieHeader(USER, false)).toContain('SameSite=Lax');
    expect(sessionCookieHeader(USER, false)).not.toContain('Secure');
    expect(sessionCookieHeader(USER, true)).toContain('Secure');
  });

  it('carries a verifiable session', () => {
    const header = sessionCookieHeader(USER, true);
    const value = header.split(';')[0].replace('appSession=', '');
    expect(readSessionValue(value)).toEqual(USER);
  });
});
