/**
 * Signed session cookies.
 *
 * The session cookie is the only thing standing between a request and a user's
 * identity, so it has to be unforgeable. It used to be plain JSON: anyone who
 * could send an HTTP request with a `Cookie:` header of their choosing — curl
 * is enough, HttpOnly does not stop it — could claim any `sub` they liked,
 * including an admin's. There was nothing to check.
 *
 * Now the cookie is `base64url(payload).base64url(HMAC-SHA256(payload))` keyed
 * on `SESSION_SECRET`, and the payload carries its own expiry so a captured
 * cookie cannot outlive it by simply being replayed with a fresh `Max-Age`.
 * Verification is constant-time and fails closed: no secret, bad signature, or
 * past `exp` all mean "not signed in".
 */
import { createHmac, timingSafeEqual } from 'node:crypto';

export const SESSION_COOKIE = 'appSession';
export const SESSION_MAX_AGE = 60 * 60 * 24 * 7; // 7 days

export interface SessionUser {
  sub: string;
  email: string;
  name: string;
  picture?: string;
}

interface SessionPayload extends SessionUser {
  /** Seconds since the epoch, checked on every read. */
  exp: number;
}

function sessionSecret(): string {
  const secret = process.env.SESSION_SECRET;
  if (!secret) {
    throw new Error('SESSION_SECRET is not configured');
  }
  return secret;
}

function signPayload(encodedPayload: string): string {
  return createHmac('sha256', sessionSecret()).update(encodedPayload).digest('base64url');
}

/** Serialize + sign a session. Throws if SESSION_SECRET is missing. */
export function createSessionValue(user: SessionUser, now: number = Date.now()): string {
  const payload: SessionPayload = {
    sub: user.sub,
    email: user.email,
    name: user.name,
    picture: user.picture,
    exp: Math.floor(now / 1000) + SESSION_MAX_AGE,
  };

  const encoded = Buffer.from(JSON.stringify(payload), 'utf8').toString('base64url');
  return `${encoded}.${signPayload(encoded)}`;
}

/** Verify a cookie value and return its user, or null if it cannot be trusted. */
export function readSessionValue(
  value: string | undefined,
  now: number = Date.now()
): SessionUser | null {
  if (!value) {
    return null;
  }

  const separator = value.lastIndexOf('.');
  if (separator < 1) {
    return null;
  }

  const encoded = value.slice(0, separator);
  const provided = value.slice(separator + 1);

  let expected: string;
  try {
    expected = signPayload(encoded);
  } catch (error) {
    // No SESSION_SECRET: refuse every session rather than trust an unsigned one.
    console.error('Session verification is not configured:', error);
    return null;
  }

  const providedBytes = Buffer.from(provided, 'base64url');
  const expectedBytes = Buffer.from(expected, 'base64url');
  if (
    providedBytes.length !== expectedBytes.length ||
    !timingSafeEqual(providedBytes, expectedBytes)
  ) {
    return null;
  }

  let payload: SessionPayload;
  try {
    payload = JSON.parse(Buffer.from(encoded, 'base64url').toString('utf8'));
  } catch {
    return null;
  }

  if (!payload?.sub || !payload?.email) {
    return null;
  }

  if (typeof payload.exp !== 'number' || payload.exp * 1000 <= now) {
    return null;
  }

  return {
    sub: payload.sub,
    email: payload.email,
    name: payload.name,
    picture: payload.picture,
  };
}

/**
 * The full Set-Cookie header for a fresh session.
 *
 * `Secure` is set whenever the request arrived over HTTPS, so production (behind
 * nginx TLS) gets it without breaking http://localhost in dev.
 */
export function sessionCookieHeader(user: SessionUser, secure: boolean): string {
  return [
    `${SESSION_COOKIE}=${createSessionValue(user)}`,
    'Path=/',
    `Max-Age=${SESSION_MAX_AGE}`,
    'HttpOnly',
    'SameSite=Lax',
    ...(secure ? ['Secure'] : []),
  ].join('; ');
}
