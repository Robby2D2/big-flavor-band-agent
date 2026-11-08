import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { FULL_MIX_STEM_ID, useProcessingQueue } from '@/hooks/useProcessingQueue';

const SONG_ID = 1140;
const VERSION_ID = 52;

const VOCALS = 901;
const DRUMS = 902;
const OTHER = 903;

const TOOLS = [
  {
    name: 'match_tempo',
    summary: 'Time-stretch audio to a target BPM without changing pitch.',
    applies_to_file: true,
    hidden_from_editor: false,
    params: [
      { name: 'target_bpm', type: 'number', default: null, required: true, label: 'Target BPM' },
    ],
  },
  {
    name: 'remove_artifacts',
    summary: 'Detect and remove clicks, pops, and digital glitches.',
    applies_to_file: true,
    hidden_from_editor: false,
    params: [{ name: 'sensitivity', type: 'number', default: 0.5 }],
  },
];

function stem(id: number, name: string, instruments: Array<{ label: string; score: number }> = []) {
  return { id, name, display_name: null, instruments, silent: false, tagged: true };
}

function completeSet() {
  return {
    id: 9,
    status: 'complete',
    source_version_id: VERSION_ID,
    stems: [stem(VOCALS, 'vocals'), stem(DRUMS, 'drums'), stem(OTHER, 'other')],
  };
}

/**
 * The produce API, with a finished pass whose every row reported `results` —
 * which tools get measured where is the server's call (tests/test_analysis_jobs.py).
 */
function installFakeApi(results: Record<string, any> = {}) {
  const rowIds = [FULL_MIX_STEM_ID, VOCALS, DRUMS, OTHER];
  const pass = {
    status: 'complete',
    stem_set_id: 9,
    rows: rowIds.map((row_id) => ({ row_id, label: String(row_id), done: 5, total: 5 })),
    outcomes: rowIds.flatMap((row_id) =>
      Object.entries(results).map(([tool, result]) => ({ row_id, tool, result }))
    ),
  };
  const json = (data: unknown) =>
    ({ ok: true, status: 200, text: async () => JSON.stringify(data) }) as Response;

  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url === `/api/produce/songs/${SONG_ID}/stems`) return json({ stem_sets: [completeSet()] });
      if (url === '/api/produce/tools') return json({ tools: TOOLS });
      if (url.startsWith(`/api/produce/versions/${VERSION_ID}/analysis`)) return json(pass);
      return json({});
    })
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function analyzed(results: Record<string, any> = {}) {
  installFakeApi(results);
  const hook = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(100);
  });
  await act(async () => {
    await hook.result.current.ensureToolParams();
  });
  return { result: hook.result };
}

describe('the analysis pass', () => {
  it('turns a recommended clicks result into a card with its measured params', async () => {
    const { result } = await analyzed({
      remove_artifacts: {
        recommended: true,
        confidence: 'high',
        reason: '4 clicks detected (1.2 per minute)',
        findings: { count: 4, per_minute: 1.2 },
        params: { sensitivity: 0.012 },
      },
    });

    const fix = result.current.fixesForStem(DRUMS).find((f) => f.tool === 'remove_artifacts');
    expect(fix?.source).toBe('analysis');
    expect(fix?.confidence).toBe('high');
    expect(fix?.currentParams).toEqual({ sensitivity: 0.012 });
    expect(fix?.body).toContain('in this stem');
  });
});

describe('a hand-added tempo card', () => {
  // correct_beats reports the song's tempo whether or not it recommends
  // correcting the grid, which is what there is to seed from.
  const beatsButNotRecommended = {
    correct_beats: {
      recommended: false,
      reason: 'Beat grid too sparse/low-confidence to correct reliably',
      findings: { detected_bpm: 118.5, beats_detected: 40 },
      params: {},
    },
  };

  it('starts from the tempo the analysis measured, so it is runnable at once', async () => {
    const { result } = await analyzed(beatsButNotRecommended);

    act(() => result.current.addManualFix(VOCALS, 'match_tempo'));
    const fix = result.current.fixesForStem(VOCALS).find((f) => f.tool === 'match_tempo')!;

    expect(fix.currentParams.target_bpm).toBe(118.5);
    expect(result.current.missingParamsFor(fix)).toEqual([]);
    expect(result.current.incompleteFixIds.has(fix.id)).toBe(false);
  });

  it('seeds the full-mix row from the stems, which are the same performance', async () => {
    // The master analysis list has no beat detector, so without this the full
    // mix could only ever offer a card in the "needs setup" state.
    const { result } = await analyzed(beatsButNotRecommended);

    act(() => result.current.addManualFix(FULL_MIX_STEM_ID, 'match_tempo'));
    const fix = result.current.masterFixes.find((f) => f.tool === 'match_tempo')!;

    expect(fix.currentParams.target_bpm).toBe(118.5);
    expect(result.current.incompleteFixIds.has(fix.id)).toBe(false);
  });

  it('still says what it needs when nothing measured a tempo', async () => {
    const { result } = await analyzed();

    act(() => result.current.addManualFix(VOCALS, 'match_tempo'));
    const fix = result.current.fixesForStem(VOCALS).find((f) => f.tool === 'match_tempo')!;

    expect(result.current.missingParamsFor(fix).map((p) => p.name)).toEqual(['target_bpm']);
  });
});
