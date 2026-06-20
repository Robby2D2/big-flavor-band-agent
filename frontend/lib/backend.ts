/**
 * Headers the BFF sends to the FastAPI backend to cross its trust boundary.
 *
 * The backend rejects any request that does not carry the shared service secret
 * (proving the caller is this trusted BFF, not an arbitrary client on the Docker
 * network) and gates protected routes on the forwarded caller role. The route
 * handler has already authenticated the user via `requireAuth(...)`, so the role
 * it passes here is the verified role.
 */
export function backendAuthHeaders(role: string): Record<string, string> {
  const secret = process.env.BACKEND_API_SECRET;
  if (!secret) {
    throw new Error('BACKEND_API_SECRET is not configured');
  }
  return {
    'X-Service-Secret': secret,
    'X-User-Role': role,
  };
}
