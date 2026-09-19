import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import {
  FULL_MIX_STEM_ID,
  isPitchAnalyzable,
  useProcessingQueue,
  type StemInfo,
} from '@/hooks/useProcessingQueue';

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
 * The produce API, recording every analyze call so a test can assert on which
 * tool was measured against which row — the point of the pitch scoping is the
 * requests that are *not* made.
 */
function installFakeApi(results: Record<string, any> = {}) {
  const analyzed: Array<{ tool: string; row: number }> = [];
  const json = (data: unknown) =>
    ({ ok: true, status: 200, text: async () => JSON.stringify(data) }) as Response;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === `/api/produce/songs/${SONG_ID}/stems`) return json({ stem_sets: [completeSet()] });
    if (url === '/api/produce/tools') return json({ tools: TOOLS });
    const match = url.match(/^\/api\/produce\/tools\/([^/]+)\/analyze$/);
    if (match) {
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      analyzed.push({ tool: match[1], row: body.stem_id ?? FULL_MIX_STEM_ID });
      return json({ result: results[match[1]] ?? null });
    }
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return { analyzed };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function analyzed(results: Record<string, any> = {}) {
  const api = installFakeApi(results);
  const hook = renderHook(() => useProcessingQueue(SONG_ID, VERSION_ID));
  await act(async () => {
    const running = hook.result.current.startAnalysis();
    await vi.advanceTimersByTimeAsync(20_000);
    await running;
  });
  await act(async () => {
    await hook.result.current.ensureToolParams();
  });
  return { api, result: hook.result };
}

const info = (over: Partial<StemInfo>): StemInfo => ({
  id: 1,
  name: 'other',
  displayName: null,
  instruments: [],
  silent: false,
  tagged: true,
  ...over,
});

describe('which rows are worth measuring for tuning', () => {
  it('measures a vocal stem and nothing polyphonic', () => {
    expect(isPitchAnalyzable(info({ name: 'vocals' }))).toBe(true);
    expect(isPitchAnalyzable(info({ name: 'drums' }))).toBe(false);
    expect(isPitchAnalyzable(info({ name: 'guitar' }))).toBe(false);
    expect(isPitchAnalyzable(info({ name: 'piano' }))).toBe(false);
  });

  it('leaves the bass out — the detector cannot hear that low', () => {
    // pyin's floor is C2 (~65 Hz); a real bass stem voiced 2% of the window.
    expect(isPitchAnalyzable(info({ name: 'bass' }))).toBe(false);
  });

  it('follows the tagger when a single-line instrument lands inside `other`', () => {
    expect(
      isPitchAnalyzable(info({ name: 'other', instruments: [{ label: 'Fiddle / violin', score: 0.8 }] }))
    ).toBe(true);
    expect(
      isPitchAnalyzable(info({ name: 'other', instruments: [{ label: 'Piano', score: 0.8 }] }))
    ).toBe(false);
  });

  it('never measures the full mix, which is polyphonic by definition', () => {
    expect(isPitchAnalyzable(info({ id: FULL_MIX_STEM_ID, name: 'Full mix' }))).toBe(false);
  });
});

describe('the analysis pass', () => {
  it('runs pitch only on the vocal row, and clicks on every row', async () => {
    const { api } = await analyzed();

    const pitchRows = api.analyzed.filter((c) => c.tool === 'correct_pitch').map((c) => c.row);
    expect(pitchRows).toEqual([VOCALS]);

    const clickRows = api.analyzed
      .filter((c) => c.tool === 'remove_artifacts')
      .map((c) => c.row)
      .sort((a, b) => a - b);
    expect(clickRows).toEqual([FULL_MIX_STEM_ID, VOCALS, DRUMS, OTHER].sort((a, b) => a - b));
  });

  it('never measures tempo — there is no correct BPM for a song', async () => {
    const { api } = await analyzed();
    expect(api.analyzed.some((c) => c.tool === 'match_tempo')).toBe(false);
  });

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
