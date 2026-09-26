/**
 * Talking to the FastAPI backend from the BFF: the headers that cross its trust
 * boundary, and reading the reason out of an error it sends back.
 *
 * The backend rejects any request that does not carry the shared service secret
 * (proving the caller is this trusted BFF, not an arbitrary client on the Docker
 * network) and gates protected routes on the forwarded caller role. The route
 * handler has already authenticated the user via `requireAuth(...)`, so the role
 * it passes here is the verified role.
 *
 * `userId` is the signed-in user's account id, for the routes whose authorization
 * depends on *who* is calling rather than only how privileged they are — removing a
 * queued song is allowed to whoever added it (ACCT-15, RAD-13). The backend believes
 * it only because it arrives with the service secret, so it is as trustworthy as the
 * role beside it.
 */
export function backendAuthHeaders(role: string, userId?: string): Record<string, string> {
  const secret = process.env.BACKEND_API_SECRET;
  if (!secret) {
    throw new Error('BACKEND_API_SECRET is not configured');
  }
  return {
    'X-Service-Secret': secret,
    'X-User-Role': role,
    ...(userId ? { 'X-User-Id': userId } : {}),
  };
}

/**
 * The message a backend error body carries, or null if it has nothing to say.
 *
 * The backend's centralized error handlers answer with
 * `{"error": {"code", "message"}}`, **not** FastAPI's default `{"detail": ...}`. Route
 * handlers that read `detail` therefore threw the reason away and fell back to
 * "Backend API error: Forbidden" — which is exactly the wording a refusal like "you can
 * only remove songs you added yourself" needs to survive (RAD-09). `detail` is still
 * accepted second, for any response that bypasses those handlers.
 */
export function backendErrorMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;

  const candidates: unknown[] = [
    (body as { error?: { message?: unknown } }).error?.message,
    (body as { detail?: unknown }).detail,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim() !== '') return candidate;
  }

  return null;
}
