import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// No `waitFor` on purpose: it polls on a real interval that these fake timers
// freeze, and every state change here lands inside the awaited `act()` anyway.
import { act, renderHook } from '@testing-library/react';
import { useProcessingQueue } from '@/hooks/useProcessingQueue';

const SONG_ID = 1140;
const VERSION_ID = 52;
const SEPARATE_URL = '/api/produce/stems/separate';

interface FakeSet {
  id: number;
  status: string;
  source_version_id: number | null;
  stems: any[];
}

function stemRows(setId: number) {
  return ['vocals', 'drums', 'bass', 'other'].map((name, i) => ({
    id: setId * 100 + i,
    name,
    display_name: null,
    instruments: [],
    silent: false,
    // Already tagged, so the background tag poll stays out of these tests.
    tagged: true,
  }));
}

function completeSet(id: number): FakeSet {
  return { id, status: 'complete', source_version_id: VERSION_ID, stems: stemRows(id) };
}

/**
 * Stand-in for the produce API: serves the song's stem sets, and records every
 * request so a test can assert on what the hook did (and didn't) call. A POST
 * to /separate appends a finished set, the way a real Demucs job eventually
 * would, so the polling loop terminates on its first tick.
 */
function installFakeApi(sets: FakeSet[]) {
  const calls: string[] = [];
  const json = (data: unknown) => ({ ok: true, json: async () => data }) as Response;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push(`${init?.method ?? 'GET'} ${url}`);
    if (url === `/api/produce/songs/${SONG_ID}/stems`) return json({ stem_sets: sets });
    if (url === SEPARATE_URL) {
      const created = completeSet(Math.max(0, ...sets.map((s) => s.id)) + 1);
      sets.push(created);
      return json({ stem_set: created });
    }
    // Every tool reports nothing to fix — this suite is about separation, not
    // the fix queue.
    if (url.includes('/analyze')) return json({ result: null });
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return { calls, separations: () => calls.filter((c) => c.endsWith(SEPARATE_URL)) };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/**
 * Run one pass to completion, driving the hook's 4s poll loop with fake timers
 * so a separation that "takes minutes" finishes instantly.
 */
async function runPass(pass: () => Promise<void> | void) {
  await act(async () => {
    const running = pass();
    await vi.advanceTimersByTimeAsync(20_000);
    await running;
  });
}

describe('useProcessingQueue — Start analysis vs Re-separate', () => {
  it('reuses existing stems instead of separating again', async () => {
    const api = installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(api.separations()).toHaveLength(0);
    expect(result.current.analyzed).toBe(true);
    expect(result.current.stems.map((s) => s.name)).toEqual([
      'vocals',
      'drums',
      'bass',
      'other',
    ]);
  });

  it('separates when the song has no stems yet', async () => {
    const api = installFakeApi([]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(api.separations()).toHaveLength(1);
    expect(result.current.stems).toHaveLength(4);
  });

  it('separates when the only stem set failed', async () => {
    const api = installFakeApi([
      { id: 8, status: 'failed', source_version_id: VERSION_ID, stems: [] },
    ]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(api.separations()).toHaveLength(1);
  });

  it('re-separates on demand even though complete stems exist', async () => {
    const api = installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.reseparateAndAnalyze());

    expect(api.separations()).toHaveLength(1);
    // The newer set's stems replaced the old ones.
    expect(result.current.stems[0].id).toBe(1000);
  });
});
