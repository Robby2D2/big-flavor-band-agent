import { cookies } from 'next/headers';
import { backendAuthHeaders } from './backend';
import { SESSION_COOKIE, SessionUser, readSessionValue } from './session';

export enum UserRole {
  LISTENER = 'listener',
  EDITOR = 'editor',
  ADMIN = 'admin',
}

export type User = SessionUser;

/** Lowest privilege first; a role satisfies any requirement at or below its rank. */
const ROLE_RANK: Record<string, number> = {
  [UserRole.LISTENER]: 1,
  [UserRole.EDITOR]: 2,
  [UserRole.ADMIN]: 3,
};

/** The signed-in user, or null. Returns null for any cookie that fails its signature. */
export async function getCurrentUser(): Promise<User | null> {
  const cookieStore = await cookies();
  return readSessionValue(cookieStore.get(SESSION_COOKIE)?.value);
}

/** The user's role as the backend knows it, or null if it could not be read. */
async function fetchUserRole(sub: string): Promise<string | null> {
  const response = await fetch(
    `${process.env.AGENT_API_URL}/api/users/${encodeURIComponent(sub)}/role`,
    { headers: backendAuthHeaders('listener') }
  );

  if (!response.ok) {
    return null;
  }

  const data = await response.json();
  return typeof data.role === 'string' ? data.role : null;
}

/** A signed-in user together with the role the backend confirmed for them. */
export interface Caller {
  user: User;
  role: UserRole;
}

/**
 * Require a signed-in user of at least `requiredRole`, or throw, and say which role
 * they turned out to have.
 *
 * Fails **closed**: a role that cannot be read — backend down, user row missing,
 * unrecognised role — is a refusal, not a pass. This previously fell through to
 * returning the user whenever the role lookup answered with anything but 200,
 * so a backend 404 or 500 let the caller through an admin check.
 *
 * Use this over `requireAuth` when the handler has to forward the caller's own role
 * or identity rather than a constant — a listener removing a song they queued reaches
 * the same route as an editor removing anybody's (ACCT-15).
 */
export async function requireCaller(
  requiredRole: UserRole = UserRole.LISTENER
): Promise<Caller> {
  const user = await getCurrentUser();

  if (!user) {
    throw new Error('Unauthorized: Please log in');
  }

  let role: string | null = null;
  try {
    role = await fetchUserRole(user.sub);
  } catch (error) {
    console.error('Error checking user role:', error);
  }

  if (role === null || !(role in ROLE_RANK)) {
    throw new Error('Forbidden: your role could not be verified');
  }

  if (ROLE_RANK[role] < ROLE_RANK[requiredRole]) {
    throw new Error(`Forbidden: ${requiredRole} role required`);
  }

  return { user, role: role as UserRole };
}

/** Require a signed-in user of at least `requiredRole`, or throw. */
export async function requireAuth(requiredRole: UserRole = UserRole.LISTENER): Promise<User> {
  const { user } = await requireCaller(requiredRole);
  return user;
}
