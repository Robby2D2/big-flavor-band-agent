import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { FULL_MIX_STEM_ID, useProcessingQueue } from '@/hooks/useProcessingQueue';

const SONG_ID = 1140;
const VERSION_ID = 52;
const STEM_ID = 900;

/** The registry's shape, trimmed to the tools these tests care about. */
const TOOLS = [
  {
    name: 'apply_eq',
    summary: 'Shape the sound with EQ (remove mud, add clarity).',
    applies_to_file: true,
    hidden_from_editor: false,
    params: [
      { name: 'file_path', type: 'string', default: null },
      { name: 'output_path', type: 'string', default: null },
      { name: 'low_gain_db', type: 'number', default: 0, min: -12, max: 12 },
      { name: 'presence_gain_db', type: 'number', default: 2, min: -12, max: 12 },
      { name: 'start_s', type: 'number', default: null },
      { name: 'end_s', type: 'number', default: null },
    ],
  },
  {
    name: 'remove_hum',
    summary: 'Detect and remove mains electrical hum (50/60 Hz + harmonics).',
    applies_to_file: true,
    hidden_from_editor: false,
    params: [{ name: 'fundamental_hz', type: 'number', default: 60 }],
  },
  { name: 'reduce_noise', summary: 'Remove background noise, hiss, and feedback.', applies_to_file: true, hidden_from_editor: false, params: [] },
  { name: 'correct_beats', summary: 'Beat-level tempo correction.', applies_to_file: true, hidden_from_editor: false, params: [] },
  { name: 'trim_silence', summary: 'Trim non-musical content from head and tail.', applies_to_file: true, hidden_from_editor: false, params: [] },
  { name: 'normalize_audio', summary: 'Normalize levels and apply compression.', applies_to_file: true, hidden_from_editor: false, params: [] },
  { name: 'apply_mastering', summary: 'Master audio to a target loudness.', applies_to_file: true, hidden_from_editor: false, params: [] },
  // In neither scope set, and a pipeline rather than a single effect — it must
  // never reach the picker on either count.
  { name: 'auto_clean_recording', summary: 'One-click whole-song cleanup.', applies_to_file: true, hidden_from_editor: true, params: [] },
];

function completeSet() {
  return {
    id: 9,
    status: 'complete',
    source_version_id: VERSION_ID,
    stems: [
      { id: STEM_ID, name: 'vocals', display_name: null, instruments: [], silent: false, tagged: true },
    ],
  };
}

/**
 * The produce API, with the analysis outcome under the test's control:
 * `recommends` names the tools whose analyze() comes back with a finding.
 */
function installFakeApi(recommends: string[] = []) {
  const posts: Array<{ url: string; body: any }> = [];
  const json = (data: unknown) =>
    ({ ok: true, status: 200, text: async () => JSON.stringify(data) }) as Response;

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST') {
      posts.push({ url, body: init.body ? JSON.parse(String(init.body)) : null });
    }
    if (url === `/api/produce/songs/${SONG_ID}/stems`) return json({ stem_sets: [completeSet()] });
    if (url === '/api/produce/tools') return json({ tools: TOOLS });
    const analyze = url.match(/^\/api\/produce\/tools\/([^/]+)\/analyze$/);
    if (analyze) {
      const tool = analyze[1];
      if (!recommends.includes(tool)) return json({ result: null });
      return json({
        result: {
          recommended: true,
          confidence: 'high',
          reason: 'measured',
          findings: { adjustments: [1, 2] },
          params: { low_gain_db: -3, presence_gain_db: 1 },
        },
      });
    }
    return json({});
  });
  vi.stubGlobal('fetch', fetchMock);
  return { posts };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function analyzed(recommends: string[] = []) {
  const api = installFakeApi(recommends);
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

describe('producer-added fixes', () => {
  it('offers only the row-scoped, single-file tools it has not already queued', async () => {
    const { result } = await analyzed(['apply_eq']);

    const stemTools = result.current.addableToolsForStem(STEM_ID).map((t) => t.name);
    // apply_eq is already on the stem row from the analysis, so it is not offered again.
    expect(stemTools).toEqual(['reduce_noise', 'remove_hum', 'correct_beats']);

    // The master row is scoped to the master tools — and apply_eq is queued on
    // that row too, since the same pass recommended it for the whole mix.
    const masterTools = result.current.addableToolsForStem(FULL_MIX_STEM_ID).map((t) => t.name);
    expect(masterTools).toEqual(['trim_silence', 'normalize_audio', 'apply_mastering']);
    expect(masterTools).not.toContain('auto_clean_recording');
    expect(masterTools).not.toContain('correct_beats');
  });

  it('adds one enabled card starting from the tool declared defaults', async () => {
    const { result } = await analyzed();

    act(() => result.current.addManualFix(STEM_ID, 'apply_eq'));

    const fixes = result.current.fixesForStem(STEM_ID);
    expect(fixes).toHaveLength(1);
    expect(fixes[0]).toMatchObject({
      id: `stem:${STEM_ID}:apply_eq`,
      scope: 'stem',
      stemId: STEM_ID,
      tool: 'apply_eq',
      source: 'manual',
      confidence: null,
      enabled: true,
    });
    // Plumbing and region bounds are the server's business, not a card's.
    expect(fixes[0].currentParams).toEqual({ low_gain_db: 0, presence_gain_db: 2 });
    expect(fixes[0].body).toContain('You added this');
    // Adding it again is a no-op rather than a second card with the same id.
    act(() => result.current.addManualFix(STEM_ID, 'apply_eq'));
    expect(result.current.fixesForStem(STEM_ID)).toHaveLength(1);
  });

  it('adds a full-mix pick as a master-scoped fix', async () => {
    const { result } = await analyzed();

    act(() => result.current.addManualFix(FULL_MIX_STEM_ID, 'apply_mastering'));

    expect(result.current.masterFixes.map((f) => f.id)).toEqual(['master:apply_mastering']);
    expect(result.current.masterFixes[0].stemId).toBeNull();
  });

  it('sends an added fix in the accepted chain, and drops it again on remove', async () => {
    const { api, result } = await analyzed();

    act(() => result.current.addManualFix(STEM_ID, 'remove_hum'));
    act(() => result.current.updateFixParams(`stem:${STEM_ID}:remove_hum`, { fundamental_hz: 50 }));
    await act(async () => {
      await result.current.acceptAll(false);
    });

    const accepted = api.posts.filter((p) => p.url.endsWith('/accept-fixes/start'));
    expect(accepted.at(-1)!.body.stems).toEqual([
      { stem_id: STEM_ID, fixes: [{ tool: 'remove_hum', params: { fundamental_hz: 50 } }] },
    ]);

    act(() => result.current.removeFix(`stem:${STEM_ID}:remove_hum`));
    expect(result.current.fixesForStem(STEM_ID)).toHaveLength(0);
    await act(async () => {
      await result.current.acceptAll(false);
    });
    expect(api.posts.filter((p) => p.url.endsWith('/accept-fixes/start')).at(-1)!.body.stems).toEqual([
      { stem_id: STEM_ID, fixes: [] },
    ]);
  });

  it('will not remove a recommended fix — those are toggled, not deleted', async () => {
    const { result } = await analyzed(['apply_eq']);

    act(() => result.current.removeFix(`stem:${STEM_ID}:apply_eq`));

    expect(result.current.fixesForStem(STEM_ID).map((f) => f.id)).toEqual([
      `stem:${STEM_ID}:apply_eq`,
    ]);
  });

  it('keeps an added fix through a re-analysis that still finds nothing', async () => {
    const { result } = await analyzed();

    act(() => result.current.addManualFix(STEM_ID, 'reduce_noise'));
    await act(async () => {
      await result.current.analyzeStem(STEM_ID);
    });

    expect(result.current.fixesForStem(STEM_ID).map((f) => f.id)).toEqual([
      `stem:${STEM_ID}:reduce_noise`,
    ]);
    expect(result.current.fixesForStem(STEM_ID)[0].source).toBe('manual');
  });

  it('merges to one recommended card, keeping the params the producer had tuned', async () => {
    const { api, result } = await analyzed();

    act(() => result.current.addManualFix(STEM_ID, 'apply_eq'));
    act(() =>
      result.current.updateFixParams(`stem:${STEM_ID}:apply_eq`, { presence_gain_db: 6 })
    );

    // The next pass measures the imbalance the producer had already heard.
    installFakeApi(['apply_eq']);
    await act(async () => {
      await result.current.analyzeStem(STEM_ID);
    });

    const fixes = result.current.fixesForStem(STEM_ID);
    expect(fixes).toHaveLength(1);
    expect(fixes[0].source).toBe('analysis');
    expect(fixes[0].confidence).toBe('high');
    // The analysis's own number for the param they never touched; theirs for
    // the one they did.
    expect(fixes[0].currentParams).toEqual({ low_gain_db: -3, presence_gain_db: 6 });
    expect(fixes[0].suggestedParams).toEqual({ low_gain_db: -3, presence_gain_db: 1 });
    expect(api.posts).toBeDefined();
  });

  it('keeps added fixes across a whole re-analysis pass', async () => {
    const { result } = await analyzed();

    act(() => result.current.addManualFix(STEM_ID, 'remove_hum'));
    act(() => result.current.addManualFix(FULL_MIX_STEM_ID, 'apply_mastering'));

    await act(async () => {
      const running = result.current.startAnalysis();
      await vi.advanceTimersByTimeAsync(20_000);
      await running;
    });

    expect(result.current.fixesForStem(STEM_ID).map((f) => f.id)).toEqual([
      `stem:${STEM_ID}:remove_hum`,
    ]);
    expect(result.current.masterFixes.map((f) => f.id)).toEqual(['master:apply_mastering']);
  });
});
