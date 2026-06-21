import { cookies } from 'next/headers';

export enum UserRole {
  LISTENER = 'listener',
  EDITOR = 'editor',
  ADMIN = 'admin',
}

export interface User {
  sub: string;
  email: string;
  name: string;
  picture?: string;
}

export async function getCurrentUser(): Promise<User | null> {
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get('appSession');

  if (!sessionCookie) {
    return null;
  }

  try {
    // The session cookie contains the user data directly (sub, email, name, picture)
    // It may be URL-encoded, so decode it first
    const decodedValue = decodeURIComponent(sessionCookie.value);
    const session = JSON.parse(decodedValue);

    // Session contains user data directly, not under a 'user' property
    if (session.sub && session.email) {
      return {
        sub: session.sub,
        email: session.email,
        name: session.name,
        picture: session.picture,
      };
    }
    return null;
  } catch (error) {
    console.error('Error parsing session cookie:', error);
    return null;
  }
}

export async function requireAuth(requiredRole: UserRole = UserRole.LISTENER): Promise<User> {
  const user = await getCurrentUser();

  if (!user) {
    throw new Error('Unauthorized: Please log in');
  }

  // Fetch user role from backend
  try {
    const response = await fetch(`${process.env.AGENT_API_URL}/api/users/${user.sub}/role`);
    if (response.ok) {
      const data = await response.json();
      const userRole = data.role as UserRole;

      // Check role hierarchy
      const roleHierarchy: Record<UserRole, number> = {
        [UserRole.LISTENER]: 1,
        [UserRole.EDITOR]: 2,
        [UserRole.ADMIN]: 3,
      };

      if (roleHierarchy[userRole] < roleHierarchy[requiredRole]) {
        throw new Error(`Forbidden: ${requiredRole} role required`);
      }
    }
  } catch (error) {
    console.error('Error checking user role:', error);
    // If we can't check the role and it's not LISTENER, deny access
    if (requiredRole !== UserRole.LISTENER) {
      throw new Error(`Forbidden: ${requiredRole} role required`);
    }
  }

  return user;
}
