/**
 * Tests for the chunked session upload (lib/sessionUpload.ts).
 *
 * The chunking is what makes a multi-gigabyte upload possible at all through a
 * proxy that caps bodies at 100 MB, so the parts worth testing are the byte
 * arithmetic (no gaps, no overlaps, nothing sent twice) and the retry rule —
 * a retry must rewrite the same offset, or the session zip is corrupted by
 * duplicated bytes and nothing downstream can unpack it.
 */
import { describe, expect, it, vi } from 'vitest';

import {
  CHUNK_RETRIES,
  chunkRanges,
  progressFor,
  uploadSession,
} from '@/lib/sessionUpload';

describe('chunkRanges', () => {
  it('covers the whole file with no gaps or overlaps', () => {
    const ranges = chunkRanges(250, 100);

    expect(ranges).toEqual([
      { start: 0, end: 100 },
      { start: 100, end: 200 },
      { start: 200, end: 250 },
    ]);
  });

  it('sends a file smaller than one chunk as a single piece', () => {
    expect(chunkRanges(10, 100)).toEqual([{ start: 0, end: 10 }]);
  });

  it('does not split a file that is exactly one chunk', () => {
    expect(chunkRanges(100, 100)).toEqual([{ start: 0, end: 100 }]);
  });

  it('has nothing to send for an empty file', () => {
    expect(chunkRanges(0, 100)).toEqual([]);
  });
});

describe('progressFor', () => {
  it('reports a percentage of the whole file', () => {
    expect(progressFor(50, 200).percent).toBe(25);
  });

  it('never reports NaN for a zero-length file', () => {
    expect(progressFor(0, 0).percent).toBe(0);
  });
});

/** A File stand-in: jsdom's Blob.slice is enough for what the uploader does. */
function fakeFile(size: number, name = '20260501 A Session.zip'): File {
  const blob = new Blob([new Uint8Array(size)]);
  return Object.assign(blob, { name, lastModified: 0 }) as File;
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe('uploadSession', () => {
  it('opens a session, sends every chunk, then starts the scan', async () => {
    const calls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      calls.push(url as string);
      if (url === '/api/produce/sessions') return jsonResponse({ id: 7 });
      if ((url as string).endsWith('/complete')) {
        return jsonResponse({ id: 7, status: 'running' });
      }
      return jsonResponse({ received: 1 });
    }) as unknown as typeof fetch;

    const result = await uploadSession(fakeFile(250), {
      chunkBytes: 100,
      fetchImpl,
    });

    expect(calls).toEqual([
      '/api/produce/sessions',
      '/api/produce/sessions/7/chunk?offset=0',
      '/api/produce/sessions/7/chunk?offset=100',
      '/api/produce/sessions/7/chunk?offset=200',
      '/api/produce/sessions/7/complete',
    ]);
    expect(result.status).toBe('running');
  });

  it('reports progress that ends at the file size', async () => {
    const seen: number[] = [];
    const fetchImpl = vi.fn(async (url: string) =>
      url === '/api/produce/sessions'
        ? jsonResponse({ id: 1 })
        : jsonResponse({ id: 1, status: 'running' })
    ) as unknown as typeof fetch;

    await uploadSession(fakeFile(250), {
      chunkBytes: 100,
      fetchImpl,
      onProgress: (p) => seen.push(p.uploaded),
    });

    expect(seen).toEqual([0, 100, 200, 250]);
  });

  it('retries a failed chunk at the same offset', async () => {
    // Appending instead of rewriting would corrupt the zip, so the offset must
    // not move between attempts.
    const chunkCalls: string[] = [];
    let failures = 0;
    const fetchImpl = vi.fn(async (url: string) => {
      if (url === '/api/produce/sessions') return jsonResponse({ id: 3 });
      if ((url as string).endsWith('/complete')) {
        return jsonResponse({ id: 3, status: 'running' });
      }
      chunkCalls.push(url as string);
      if (failures++ === 0) return jsonResponse({ error: 'boom' }, 500);
      return jsonResponse({ received: 1 });
    }) as unknown as typeof fetch;

    await uploadSession(fakeFile(100), { chunkBytes: 100, fetchImpl });

    expect(chunkCalls).toEqual([
      '/api/produce/sessions/3/chunk?offset=0',
      '/api/produce/sessions/3/chunk?offset=0',
    ]);
  });

  it('gives up on a chunk the server refuses outright', async () => {
    // A 409 means the session is no longer accepting an upload; retrying it
    // cannot help and would just delay the error.
    let attempts = 0;
    const fetchImpl = vi.fn(async (url: string) => {
      if (url === '/api/produce/sessions') return jsonResponse({ id: 4 });
      attempts++;
      return jsonResponse({ error: 'Session is running, not uploading' }, 409);
    }) as unknown as typeof fetch;

    await expect(
      uploadSession(fakeFile(100), { chunkBytes: 100, fetchImpl })
    ).rejects.toThrow('not uploading');
    expect(attempts).toBe(1);
  });

  it('stops after the retry budget on a persistent server error', async () => {
    let attempts = 0;
    const fetchImpl = vi.fn(async (url: string) => {
      if (url === '/api/produce/sessions') return jsonResponse({ id: 5 });
      attempts++;
      return jsonResponse({ error: 'still broken' }, 503);
    }) as unknown as typeof fetch;

    await expect(
      uploadSession(fakeFile(100), { chunkBytes: 100, fetchImpl })
    ).rejects.toThrow('still broken');
    expect(attempts).toBe(CHUNK_RETRIES);
  });

  it('surfaces a refusal to open the session', async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ error: 'Access denied' }, 403)
    ) as unknown as typeof fetch;

    await expect(
      uploadSession(fakeFile(100), { fetchImpl })
    ).rejects.toThrow('Access denied');
  });
});
