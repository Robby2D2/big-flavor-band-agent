/**
 * The lyrics BFF route: what SongList's "view lyrics" modal actually calls.
 *
 * The structural check in bffRoutes.test.ts proves the route exists; this proves
 * it behaves — passes the backend's lyrics through, and turns an auth failure
 * into a status the modal can distinguish from "this song has no lyrics".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const requireAuth = vi.fn();

vi.mock('@/lib/server-auth', () => ({
  requireAuth: (...args: unknown[]) => requireAuth(...args),
  UserRole: { LISTENER: 'listener', EDITOR: 'editor', ADMIN: 'admin' },
}));

const { GET } = await import('@/app/api/songs/[songId]/lyrics/route');

const params = Promise.resolve({ songId: '1299' });

function backendReturns(status: number, body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(body), { status }))
  );
}

beforeEach(() => {
  requireAuth.mockReset();
  requireAuth.mockResolvedValue({ sub: 'u1', email: 'a@b.com', name: 'A' });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('GET /api/songs/[songId]/lyrics', () => {
  it('returns the lyrics the backend holds', async () => {
    backendReturns(200, { lyrics: "It's the middle of the night" });

    const response = await GET({} as never, { params });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ lyrics: "It's the middle of the night" });
  });

  it('asks for a listener, not an editor — lyrics are readable by anyone signed in', async () => {
    backendReturns(200, { lyrics: 'words' });

    await GET({} as never, { params });

    expect(requireAuth).toHaveBeenCalledWith('listener');
  });

  it('calls the backend lyrics endpoint for the requested song', async () => {
    backendReturns(200, { lyrics: 'words' });

    await GET({} as never, { params });

    const [url] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toMatch(/\/api\/songs\/1299\/lyrics$/);
  });

  it('passes a backend 404 through rather than reporting success', async () => {
    backendReturns(404, { detail: 'Song not found' });

    const response = await GET({} as never, { params });

    expect(response.status).toBe(404);
    expect((await response.json()).error).toBe('Song not found');
  });

  it('answers 401 when nobody is signed in', async () => {
    requireAuth.mockRejectedValue(new Error('Unauthorized: Please log in'));

    const response = await GET({} as never, { params });

    expect(response.status).toBe(401);
  });

  it('answers 403 when the role is insufficient or unverifiable', async () => {
    requireAuth.mockRejectedValue(new Error('Forbidden: your role could not be verified'));

    const response = await GET({} as never, { params });

    expect(response.status).toBe(403);
  });
});
