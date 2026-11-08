import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// No `waitFor` on purpose: it polls on a real interval that these fake timers
// freeze, and every state change here lands inside the awaited `act()` anyway.
import { act, renderHook } from '@testing-library/react';
import { FULL_MIX_STEM_ID, useProcessingQueue } from '@/hooks/useProcessingQueue';

const SONG_ID = 1140;
const VERSION_ID = 52;
const OTHER_VERSION = 51;
const SEPARATE_URL = '/api/produce/stems/separate';
const PASS_URL = `/api/produce/versions/${VERSION_ID}/analysis`;
const START_URL = `${PASS_URL}/start`;

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

/** A finished pass over one set: every row measured, nothing recommended. */
function finishedPass(setId: number, stems = stemRows(setId)) {
  return {
    status: 'complete',
    stem_set_id: setId,
    stage: null,
    rows: [
      { row_id: FULL_MIX_STEM_ID, label: 'Full mix', done: 5, total: 5 },
      ...stems.map((s) => ({ row_id: s.id, label: s.name, done: 5, total: 5 })),
    ],
    outcomes: [],
    error: null,
  };
}

/**
 * Stand-in for the produce API: serves the song's stem sets and the version's
 * analysis pass, and records every request so a test can assert on what the
 * hook did (and didn't) call. A POST to /separate appends a finished set, the
 * way a real Demucs job eventually would, so the polling loop terminates on its
 * first tick. `pass` is what the server currently says about the version.
 */
function installFakeApi(sets: FakeSet[], initialPass: any = { status: 'idle' }) {
  const calls: string[] = [];
  const api = {
    calls,
    pass: initialPass,
    separations: () => calls.filter((c) => c.endsWith(SEPARATE_URL)),
  };
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
    if (url === START_URL) {
      api.pass = finishedPass(sets[0]?.id ?? 9);
      return json(api.pass);
    }
    if (url === `${PASS_URL}/cancel`) return json({ status: 'running' });
    if (url === PASS_URL) return json(api.pass);
    if (url === `/api/produce/versions/${OTHER_VERSION}/analysis`) return json({ status: 'idle' });
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return api;
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
  await settle();
}

/** Let the mount effects and the pass poll run, as a page load would. */
async function settle(ms = 100) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useProcessingQueue — Start analysis', () => {
  it('hands the pass to the server and measures nothing itself', async () => {
    const api = installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(api.calls).toContain(`POST ${START_URL}`);
    expect(api.calls.some((c) => c.includes('/tools/'))).toBe(false);
    expect(api.separations()).toHaveLength(0);
    expect(result.current.analyzed).toBe(true);
    expect(result.current.analyzing).toBe(false);
    expect(result.current.stems.map((s) => s.name)).toEqual(['vocals', 'drums', 'bass', 'other']);
  });

  it('reports a pass it started when that pass finishes', async () => {
    installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await runPass(() => result.current.startAnalysis());

    expect(result.current.analysisTask?.status).toBe('done');
  });

  it('shows the error and stops when the server will not start a pass', async () => {
    installFakeApi([completeSet(9)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));
    await settle();

    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: false,
        status: 503,
        text: async () => JSON.stringify({ error: 'Production tools not available' }),
      }))
    );
    await runPass(() => result.current.startAnalysis());

    expect(result.current.error).toBe('Production tools not available');
    expect(result.current.analyzing).toBe(false);
  });

  it('asks the server to cancel, and keeps following until it has', async () => {
    const api = installFakeApi([completeSet(9)], {
      status: 'running',
      stage: 'measuring',
      stem_set_id: 9,
      rows: [{ row_id: 900, label: 'vocals', done: 1, total: 6 }],
    });
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));
    await settle();

    await act(async () => {
      await result.current.cancelAnalysis();
    });
    expect(api.calls).toContain(`POST ${PASS_URL}/cancel`);
    expect(result.current.analyzing).toBe(true);

    api.pass = { ...api.pass, status: 'cancelled', outcomes: [] };
    await settle(4_100);
    expect(result.current.analyzing).toBe(false);
    expect(result.current.analysisTask?.status).toBe('cancelled');
  });
});

// The whole point: the page can be closed mid-pass, because the server has it.
describe('useProcessingQueue — leaving and coming back', () => {
  const recommended = {
    row_id: 900,
    tool: 'remove_hum',
    result: {
      recommended: true,
      confidence: 'high',
      reason: 'hum',
      findings: {},
      params: { fundamental_hz: 60 },
    },
  };

  it('restores what a finished pass found, without being asked', async () => {
    const pass = { ...finishedPass(9), outcomes: [recommended] };
    const api = installFakeApi([completeSet(9)], pass);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await settle();

    expect(api.calls).not.toContain(`POST ${START_URL}`);
    expect(result.current.analyzed).toBe(true);
    expect(result.current.fixesForStem(900).map((f) => f.tool)).toEqual(['remove_hum']);
    expect(result.current.fixesForStem(900)[0].currentParams).toEqual({ fundamental_hz: 60 });
    expect(result.current.analyzedStemIds.has(900)).toBe(true);
    // Nothing just happened, so nothing is announced.
    expect(result.current.analysisTask).toBeNull();
  });

  it('picks a running pass back up, and takes its findings when it lands', async () => {
    const running = {
      status: 'running',
      stage: 'measuring',
      stem_set_id: 9,
      rows: [
        { row_id: FULL_MIX_STEM_ID, label: 'Full mix', done: 5, total: 5 },
        { row_id: 900, label: 'vocals', done: 2, total: 6 },
      ],
    };
    const api = installFakeApi([completeSet(9)], running);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await settle();
    expect(result.current.analyzing).toBe(true);
    expect(result.current.analysisTask?.status).toBe('running');
    expect(result.current.analysisTask?.rows[1].done).toBe(2);
    expect(result.current.stems).toHaveLength(4);

    api.pass = { ...finishedPass(9), outcomes: [recommended] };
    await settle(4_100);

    expect(result.current.analyzing).toBe(false);
    expect(result.current.analyzed).toBe(true);
    expect(result.current.fixesForStem(900)).toHaveLength(1);
    // This one finished while the page was watching, so it is reported.
    expect(result.current.analysisTask?.status).toBe('done');
  });

  it('shows a separation in progress, and the stems the moment they exist', async () => {
    const sets: FakeSet[] = [];
    const api = installFakeApi(sets, {
      status: 'running',
      stage: 'separating',
      stem_set_id: null,
      separation_started_at: 1_700_000_000,
      rows: [],
    });
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await settle();
    expect(result.current.separationTask?.status).toBe('running');
    expect(result.current.separationTask?.startedAt).toBe(1_700_000_000_000);
    expect(result.current.stems).toEqual([]);

    sets.push(completeSet(9));
    api.pass = { status: 'running', stage: 'measuring', stem_set_id: 9, rows: [] };
    await settle(4_100);

    expect(result.current.separationTask).toBeNull();
    expect(result.current.stems).toHaveLength(4);
  });

  it('reports a pass that failed while nobody was watching', async () => {
    installFakeApi([], { status: 'failed', stem_set_id: null, rows: [], error: 'Out of memory' });
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await settle();

    expect(result.current.separationTask?.status).toBe('failed');
    expect(result.current.separationTask?.error).toBe('Out of memory');
    expect(result.current.analyzed).toBe(false);
  });

  it('forgets a failure once it has been cleared', async () => {
    const api = installFakeApi([], { status: 'failed', stem_set_id: null, rows: [], error: 'x' });
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));
    await settle();

    act(() => result.current.dismissTasks());

    expect(result.current.separationTask).toBeNull();
    expect(api.calls).toContain(`POST ${PASS_URL}/dismiss`);
  });

  it('calls only whole rows analyzed after a cancelled pass', async () => {
    const pass = {
      status: 'cancelled',
      stem_set_id: 9,
      rows: [
        { row_id: FULL_MIX_STEM_ID, label: 'Full mix', done: 5, total: 5 },
        { row_id: 900, label: 'vocals', done: 2, total: 6 },
      ],
      outcomes: [],
    };
    installFakeApi([completeSet(9)], pass);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    await settle();

    expect(result.current.analyzedStemIds.has(FULL_MIX_STEM_ID)).toBe(true);
    // A half-measured stem must not read as clean.
    expect(result.current.analyzedStemIds.has(900)).toBe(false);
    expect(result.current.analyzed).toBe(false);
  });

  it('stops following one version when another is selected', async () => {
    const api = installFakeApi([completeSet(9)], {
      status: 'running',
      stage: 'measuring',
      stem_set_id: 9,
      rows: [{ row_id: 900, label: 'vocals', done: 1, total: 6 }],
    });
    const { result, rerender } = renderHook(
      ({ version }) => useProcessingQueue(SONG_ID, version),
      { initialProps: { version: VERSION_ID } }
    );
    await settle();
    expect(result.current.analyzing).toBe(true);

    rerender({ version: OTHER_VERSION });
    await settle();

    expect(result.current.analyzing).toBe(false);
    expect(result.current.analysisTask).toBeNull();

    const before = api.calls.filter((c) => c === `GET ${PASS_URL}`).length;
    await settle(10_000);
    expect(api.calls.filter((c) => c === `GET ${PASS_URL}`)).toHaveLength(before);
  });
});

describe('useProcessingQueue — Separate stems', () => {
  it('shows no stems at all for a version that has none', async () => {
    const api = installFakeApi([completeSetForVersion(9, OTHER_VERSION)]);
    const { result } = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));

    // The mount preload alone, with no analysis pass: another version's stems
    // must not appear just because they are the song's newest.
    await settle();

    expect(result.current.stems).toEqual([]);
    expect(api.separations()).toHaveLength(0);
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
    // The server retires findings once a newer set exists.
    api.pass = { status: 'idle' };

    await runPass(() => result.current.separateStems());

    // Those fixes were measurements of audio that no longer exists.
    expect(result.current.analyzed).toBe(false);
    expect(result.current.fixes).toEqual([]);
    expect(api.separations()).toHaveLength(1);
  });

});
