/**
 * Server-side half of the invite flow.
 *
 * An invite link carries a token that is useless on its own: redeeming it
 * requires signing in with Google as the exact address the invite was issued
 * to. The token is handed to the backend from here (never from the browser),
 * and rides across the Google round-trip in a short-lived HttpOnly cookie
 * rather than in the OAuth `state`, so the existing auth route keeps its shape.
 */
import { backendAuthHeaders } from './backend';

export const INVITE_COOKIE = 'pendingInvite';

/** Long enough to finish a Google sign-in, short enough that an abandoned
 *  attempt does not leave the token sitting in the browser. */
export const INVITE_COOKIE_MAX_AGE = 60 * 10;

export type InviteStatus = 'valid' | 'revoked' | 'redeemed' | 'expired';

export interface InvitePreview {
  email: string;
  role: string;
  status: InviteStatus;
  expires_at: string;
}

export type RedeemResult =
  | { ok: true; role: string }
  | { ok: false; error: string };

async function postToBackend(path: string, body: unknown): Promise<Response> {
  return fetch(`${process.env.AGENT_API_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // The invitee has no role yet — 'listener' is the floor these two routes
      // require, so the service secret is what actually guards them.
      ...backendAuthHeaders('listener'),
    },
    body: JSON.stringify(body),
  });
}

/** Describe an invite for its landing page, or null if the link is unknown. */
export async function previewInvite(token: string): Promise<InvitePreview | null> {
  try {
    const response = await postToBackend('/api/invites/preview', { token });
    if (!response.ok) {
      return null;
    }
    return (await response.json()) as InvitePreview;
  } catch (error) {
    console.error('Invite preview failed:', error);
    return null;
  }
}

/** Apply an invite to the user who just signed in. */
export async function redeemInvite(
  token: string,
  userId: string,
  email: string
): Promise<RedeemResult> {
  try {
    const response = await postToBackend('/api/invites/redeem', {
      token,
      user_id: userId,
      email,
    });

    const data = await response.json();

    if (!response.ok) {
      return { ok: false, error: data.detail || 'This invite could not be used.' };
    }

    return { ok: true, role: data.role };
  } catch (error) {
    console.error('Invite redemption failed:', error);
    return { ok: false, error: 'Could not reach the server to accept this invite.' };
  }
}
