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

/** A finished set belonging to some *other* version of the same song. */
function completeSetForVersion(id: number, versionId: number | null): FakeSet {
  return { id, status: 'complete', source_version_id: versionId, stems: stemRows(id) };
}

/**
 * Stand-in for the produce API: serves the song's stem sets, and records every
 * request so a test can assert on what the hook did (and didn't) call. A POST
 * to /separate appends a finished set, the way a real Demucs job eventually
 * would, so the polling loop terminates on its first tick.
 */
function installFakeApi(sets: FakeSet[]) {
  const calls: string[] = [];
  // Served as text, the way the hook reads it (lib/apiJson.ts) — a real
  // response body is a string, and only the app's own bodies are JSON.
  const json = (data: unknown) =>
    ({ ok: true, status: 200, text: async () => JSON.stringify(data) }) as Response;

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

  // The bug this scoping exists to prevent: song 1144 had one stem set, from
  // the original, and selecting the cleaned version showed those stems. An
  // artifact the cleaning introduced was audible in the full-mix row and in
  // none of the stems below it, because they were a different recording.
  it('ignores a complete set that belongs to a different version', async () => {
    const OTHER_VERSION = 51;
    const api = installFakeApi([completeSetForVersion(9, OTHER_VERSION)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    // It must separate this version rather than reuse the other one's stems.
    expect(api.separations()).toHaveLength(1);
    expect(
      result.current.stems.every((stem) => stem.id >= 1000)
    ).toBe(true);
  });

  it('shows no stems at all for a version that has none', async () => {
    const api = installFakeApi([completeSetForVersion(9, 51)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    // The mount preload alone, with no analysis pass: another version's stems
    // must not appear just because they are the song's newest.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });

    expect(result.current.stems).toEqual([]);
    expect(api.separations()).toHaveLength(0);
  });

  it('leaves a legacy set with no recorded version unattributed', async () => {
    // Pre-dates source_version_id. It belongs to no version we can name, so it
    // is shown for none — migration 16 attributes the ones that can be.
    const api = installFakeApi([completeSetForVersion(9, null)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(api.separations()).toHaveLength(1);
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

  it('separates without running a measuring pass', async () => {
    // The point of the separate button: a producer who only wants the parts
    // should not have to sit through analysis to get them.
    const api = installFakeApi([]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.separateStems());

    expect(api.separations()).toHaveLength(1);
    expect(result.current.stems).toHaveLength(4);
    // Nothing was measured, so nothing claims to have been.
    expect(result.current.analyzed).toBe(false);
    expect(result.current.fixes).toEqual([]);
    expect(result.current.separating).toBe(false);
  });

  it('makes a fresh set when the version already has stems', async () => {
    const api = installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.separateStems());

    // This is what "Re-separate" used to do from inside the console.
    expect(api.separations()).toHaveLength(1);
  });

  it('drops fixes measured from the stems it just replaced', async () => {
    const api = installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());
    expect(result.current.analyzed).toBe(true);

    await runPass(() => result.current.separateStems());

    // Those fixes were measurements of audio that no longer exists.
    expect(result.current.analyzed).toBe(false);
    expect(result.current.fixes).toEqual([]);
    expect(api.separations()).toHaveLength(1);
  });

});
