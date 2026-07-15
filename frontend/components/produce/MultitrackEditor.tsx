'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import WaveformView from './WaveformView';
import StemMixer from './StemMixer';
import { decodeAudio, formatTime, Region } from './audioEngine';

interface VersionOption {
  id: number;
  name: string;
  is_published: boolean;
}

interface MultitrackEditorProps {
  songId: number;
  /** Versions available to start from; the editor owns which one is active. */
  versions: VersionOption[];
  /** Called after a new candidate version is created, to refresh the list. */
  onApplied: () => void;
}

type SelectionMode = 'whole' | 'region';
type ToolKey = 'trim' | 'noise_reduction' | 'pitch' | 'tempo' | 'eq';
type Intensity = 'gentle' | 'moderate' | 'aggressive';

const TOOLS: { key: ToolKey; label: string; help: string }[] = [
  { key: 'trim', label: 'Trim to selection', help: 'Keep only the selected span, discarding audio outside it.' },
  { key: 'noise_reduction', label: 'Reduce noise', help: 'Remove steady background noise from the selection (or sample it as the noise profile).' },
  { key: 'pitch', label: 'Pitch correction', help: 'Key-aware auto-tune over the selection; strength is the retune amount.' },
  { key: 'tempo', label: 'Tempo / beat correction', help: 'Quantize beats to a steady tempo. Whole-file by design; strength is the correction amount.' },
  { key: 'eq', label: 'EQ / cleanup', help: 'Apply EQ (high-pass, low-pass, and a boost band) over the selection.' },
];

// Whole-file tools ignore the region; the rest require a selection to act on.
const WHOLE_FILE_TOOLS: ToolKey[] = ['tempo'];

// The whole-song cleanup steps, in processing order. Keys match the backend
// steps_override map (trim / noise_reduction / eq / normalize / master).
const STEPS: { key: string; label: string; help: string }[] = [
  {
    key: 'trim',
    label: 'Trim non-musical content',
    help: 'Cuts the silence, noise, or talking detected before the music starts and after it ends, so the track begins and finishes on the music.',
  },
  {
    key: 'noise_reduction',
    label: 'Reduce noise',
    help: 'Removes steady background noise such as hiss, hum, or room tone. How hard it is applied depends on the Intensity setting.',
  },
  {
    key: 'eq',
    label: 'Apply EQ corrections',
    help: 'Balances the frequencies: filters out low rumble, tames a boomy or muddy low end, and adds clarity (or softens harsh highs) based on the analysis.',
  },
  {
    key: 'normalize',
    label: 'Normalize',
    help: 'Raises the track to a consistent volume and evens out the loud and quiet parts with light compression. Intensity sets how strong that compression is.',
  },
  {
    key: 'master',
    label: 'Master',
    help: 'A final polish that brings the track up to a standard, cohesive loudness so it sits well alongside other songs.',
  },
];

const INTENSITY_HELP =
  'How strongly the enabled steps are applied. Gentle is a light touch (less noise reduction, EQ, and compression), Moderate is the balanced default, and Aggressive pushes each effect harder for noisier or more uneven recordings.';

interface ToolParams {
  // pitch
  key?: string;
  chromatic?: boolean;
  // tempo
  target_bpm?: number;
  // noise_reduction
  non_stationary?: boolean;
  noise_from_selection?: boolean;
  // eq
  high_pass_freq?: number;
  low_pass_freq?: number;
  boost_freq?: number;
  boost_db?: number;
}

function InfoTip({ text, label }: { text: string; label: string }) {
  return (
    <span
      title={text}
      aria-label={`${label}: ${text}`}
      tabIndex={0}
      className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-gray-400 dark:border-gray-500 text-[10px] font-semibold leading-none text-gray-500 dark:text-gray-400 cursor-help select-none focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      i
    </span>
  );
}

// Reads the backend's analyze recommendations into the steps_override map
// used by both the manual whole-song flow and the one-click shortcut.
function stepsFromAnalysis(result: any): Record<string, boolean> {
  const recs = result?.recommendations;
  if (!recs) return {};
  return {
    trim: !!recs.trim?.recommended,
    noise_reduction: !!recs.noise_reduction?.recommended,
    eq: !!recs.eq?.recommended,
    normalize: recs.normalization?.recommended ?? true,
    master: recs.mastering?.recommended ?? true,
  };
}

/**
 * Unified audio-processing panel for the produce page (issue #77): one
 * starting-version picker, a shared waveform, and a "Whole song" / "Region"
 * selection mode. Whole song reuses the version-level analyze -> recommended
 * steps/intensity -> clean flow; Region reuses the tool + strength ->
 * Preview/Apply flow from #70. A "Clean this version" shortcut runs the
 * whole-song analyze+clean in one action for non-power users. Per-stem rows
 * remain available underneath either mode.
 */
export default function MultitrackEditor({
  songId,
  versions,
  onApplied,
}: MultitrackEditorProps) {
  const [sourceVersionId, setSourceVersionId] = useState<number | null>(null);
  const [selectionMode, setSelectionMode] = useState<SelectionMode>('whole');

  const [buffer, setBuffer] = useState<AudioBuffer | null>(null);
  const [duration, setDuration] = useState(0);
  const [beats, setBeats] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Region-mode state.
  const [region, setRegion] = useState<Region | null>(null);
  const [tool, setTool] = useState<ToolKey>('trim');
  const [strength, setStrength] = useState(0.8);
  const [params, setParams] = useState<ToolParams>({});
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Whole-song mode state.
  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [intensity, setIntensity] = useState<Intensity>('moderate');
  const [stepEnabled, setStepEnabled] = useState<Record<string, boolean>>({});
  const [cleanResult, setCleanResult] = useState<any>(null);
  const [cleaning, setCleaning] = useState(false);

  // One-click shortcut state — independent of the manual whole-song flow above.
  const [quickCleaning, setQuickCleaning] = useState(false);
  const [quickMessage, setQuickMessage] = useState<string | null>(null);

  const [playhead, setPlayhead] = useState<number | null>(null);
  const originalAudioRef = useRef<HTMLAudioElement>(null);

  // Default the working source to the published version, else the first one,
  // and keep it if it's still present after a version list refresh.
  useEffect(() => {
    setSourceVersionId((prev) => {
      if (prev != null && versions.some((v) => v.id === prev)) return prev;
      const published = versions.find((v) => v.is_published);
      return published?.id ?? versions[0]?.id ?? null;
    });
  }, [versions]);

  const sourceAudioUrl =
    sourceVersionId != null
      ? `/api/produce/versions/${sourceVersionId}/audio`
      : null;

  // Load + decode the working source audio and its beat markers whenever the
  // selected version changes.
  useEffect(() => {
    if (sourceVersionId == null) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setBuffer(null);
    setRegion(null);
    setPreviewPath(null);
    setMessage(null);
    setAnalysis(null);
    setCleanResult(null);
    setQuickMessage(null);

    (async () => {
      try {
        const decoded = await decodeAudio(
          `/api/produce/versions/${sourceVersionId}/audio`
        );
        if (cancelled) return;
        setBuffer(decoded);
        setDuration(decoded.duration);
      } catch (err) {
        if (!cancelled) setLoadError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    (async () => {
      try {
        const res = await fetch(
          `/api/produce/songs/${songId}/beats?source_version_id=${sourceVersionId}`
        );
        const data = await res.json();
        if (!cancelled && res.ok) setBeats(data.beats || []);
      } catch {
        // Beat markers are optional — absence must not break the editor.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [songId, sourceVersionId]);

  const isWholeFileTool = WHOLE_FILE_TOOLS.includes(tool);
  const needsRegion = !isWholeFileTool;
  const hasRegion = region != null && region.end - region.start > 0.01;
  const canRunRegionTool =
    sourceVersionId != null &&
    buffer != null &&
    busy == null &&
    (!needsRegion || hasRegion);

  const setParam = (patch: Partial<ToolParams>) =>
    setParams((prev) => ({ ...prev, ...patch }));

  const buildRequestBody = useCallback(() => {
    // Region bounds: whole-file tools omit them. Noise "sample from selection"
    // sends the region as the noise profile and denoises the whole file.
    const start = isWholeFileTool ? null : region?.start ?? null;
    const end = isWholeFileTool ? null : region?.end ?? null;

    const outParams: Record<string, unknown> = {};
    if (tool === 'pitch') {
      if (params.key) outParams.key = params.key;
      if (params.chromatic) outParams.chromatic = true;
    } else if (tool === 'tempo') {
      if (params.target_bpm) outParams.target_bpm = params.target_bpm;
    } else if (tool === 'noise_reduction') {
      if (params.non_stationary) outParams.non_stationary = true;
    } else if (tool === 'eq') {
      if (params.high_pass_freq != null) outParams.high_pass_freq = params.high_pass_freq;
      if (params.low_pass_freq != null) outParams.low_pass_freq = params.low_pass_freq;
      if (params.boost_freq != null) outParams.boost_freq = params.boost_freq;
      if (params.boost_db != null) outParams.boost_db = params.boost_db;
    }

    let startOut = start;
    let endOut = end;
    if (tool === 'noise_reduction' && params.noise_from_selection && region) {
      outParams.noise_start_s = region.start;
      outParams.noise_end_s = region.end;
      // Sample noise from the selection but denoise the whole file.
      startOut = null;
      endOut = null;
    }

    return {
      song_id: songId,
      source_version_id: sourceVersionId,
      tool,
      start_s: startOut,
      end_s: endOut,
      strength,
      params: outParams,
    };
  }, [isWholeFileTool, region, tool, params, songId, sourceVersionId, strength]);

  const handlePreview = async () => {
    setBusy('preview');
    setMessage(null);
    setPreviewPath(null);
    try {
      const res = await fetch('/api/produce/region/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Preview failed');
      setPreviewPath(data.candidate_path);
      setMessage('Preview ready — compare it against the original below. No version was created.');
    } catch (err) {
      setMessage(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleApply = async () => {
    setBusy('apply');
    setMessage(null);
    try {
      const res = await fetch('/api/produce/region/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Apply failed');
      setMessage('Applied — saved as a new candidate version below.');
      setPreviewPath(null);
      onApplied();
    } catch (err) {
      setMessage(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleAnalyze = async () => {
    if (sourceVersionId == null) return;
    setAnalyzing(true);
    setAnalysis(null);
    setCleanResult(null);
    try {
      const response = await fetch('/api/produce/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, source_version_id: sourceVersionId }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Analysis failed');
      }
      setAnalysis(data.result);
      setStepEnabled(stepsFromAnalysis(data.result));
    } catch (err: any) {
      setAnalysis({ status: 'error', error: err.message });
    } finally {
      setAnalyzing(false);
    }
  };

  const handleClean = async () => {
    if (sourceVersionId == null) return;
    setCleaning(true);
    setCleanResult(null);
    try {
      const response = await fetch('/api/produce/auto-clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          aggressiveness: intensity,
          steps_override: stepEnabled,
          source_version_id: sourceVersionId,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Clean failed');
      }
      setCleanResult(data.result);
      if (data.result?.status === 'success') {
        onApplied();
      }
    } catch (err: any) {
      setCleanResult({ status: 'error', error: err.message });
    } finally {
      setCleaning(false);
    }
  };

  const toggleStep = (key: string) => {
    setStepEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // One-click shortcut: analyze then clean with the recommended steps at
  // moderate intensity, without touching the manual flow's picker state.
  const handleQuickClean = async () => {
    if (sourceVersionId == null) return;
    setQuickCleaning(true);
    setQuickMessage(null);
    try {
      const analyzeRes = await fetch('/api/produce/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, source_version_id: sourceVersionId }),
      });
      const analyzeData = await analyzeRes.json();
      if (!analyzeRes.ok) {
        throw new Error(analyzeData.error || 'Analysis failed');
      }
      const steps = stepsFromAnalysis(analyzeData.result);

      const cleanRes = await fetch('/api/produce/auto-clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          aggressiveness: 'moderate',
          steps_override: steps,
          source_version_id: sourceVersionId,
        }),
      });
      const cleanData = await cleanRes.json();
      if (!cleanRes.ok) {
        throw new Error(cleanData.error || 'Clean failed');
      }
      if (cleanData.result?.status !== 'success') {
        throw new Error(cleanData.result?.error || 'Clean failed');
      }
      setQuickMessage(
        `Success — ${cleanData.result.total_steps} step(s) applied. Saved as a new version below.`
      );
      onApplied();
    } catch (err) {
      setQuickMessage(`Error: ${(err as Error).message}`);
    } finally {
      setQuickCleaning(false);
    }
  };

  const analysisOk = analysis && analysis.status === 'success';

  if (versions.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No versions yet for this song.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Starting version
        </label>
        <select
          value={sourceVersionId ?? ''}
          onChange={(e) =>
            setSourceVersionId(e.target.value ? Number(e.target.value) : null)
          }
          className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.is_published ? ' (default)' : ''}
            </option>
          ))}
        </select>
      </div>

      {sourceVersionId == null ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Select a starting version above to load the editor.
        </p>
      ) : (
        <>
          {/* One-click shortcut for non-power users. */}
          <div className="flex flex-wrap items-center gap-3 mb-6 pb-6 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={handleQuickClean}
              disabled={quickCleaning}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {quickCleaning ? 'Cleaning...' : 'Clean this version'}
            </button>
            <span className="text-xs text-gray-500 dark:text-gray-400 max-w-md">
              One click: analyzes the starting version and applies the
              recommended steps at moderate intensity as a new version.
            </span>
            {quickMessage && (
              <span className="text-sm text-gray-700 dark:text-gray-300 basis-full">
                {quickMessage}
              </span>
            )}
          </div>

          {/* Selection mode */}
          <div className="flex items-center gap-2 mb-4">
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Selection
            </span>
            <div className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600 overflow-hidden text-sm">
              <button
                type="button"
                onClick={() => setSelectionMode('whole')}
                className={`px-3 py-1.5 ${
                  selectionMode === 'whole'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
                }`}
              >
                Whole song
              </button>
              <button
                type="button"
                onClick={() => setSelectionMode('region')}
                className={`px-3 py-1.5 border-l border-gray-300 dark:border-gray-600 ${
                  selectionMode === 'region'
                    ? 'bg-blue-600 text-white'
                    : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
                }`}
              >
                Region
              </button>
            </div>
          </div>

          {loading && (
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Loading waveform…</p>
          )}
          {loadError && (
            <p className="text-sm text-red-600 dark:text-red-400 mb-3">{loadError}</p>
          )}

          <WaveformView
            buffer={buffer}
            duration={duration}
            selectable={selectionMode === 'region'}
            region={
              selectionMode === 'whole'
                ? duration > 0
                  ? { start: 0, end: duration }
                  : null
                : region
            }
            onRegionChange={selectionMode === 'region' ? setRegion : undefined}
            beats={beats}
            playhead={playhead}
          />

          {selectionMode === 'region' && (
            <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-gray-600 dark:text-gray-400">
              <span>
                {region
                  ? `Selection: ${formatTime(region.start)} – ${formatTime(region.end)}`
                  : 'Drag on the waveform to select a region.'}
              </span>
              {region && (
                <button
                  onClick={() => setRegion(null)}
                  className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  Clear selection
                </button>
              )}
              {beats.length > 0 && (
                <span className="text-xs text-yellow-600 dark:text-yellow-400">
                  {beats.length} beat markers
                </span>
              )}
            </div>
          )}

          {/* Original playback drives the waveform playhead. */}
          {sourceAudioUrl && (
            <audio
              ref={originalAudioRef}
              controls
              preload="none"
              src={sourceAudioUrl}
              className="mt-3 h-9 w-full max-w-md"
              onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
              onPause={() => setPlayhead(null)}
              onEnded={() => setPlayhead(null)}
            />
          )}

          {selectionMode === 'whole' ? (
            <div className="mt-5 border-t border-gray-200 dark:border-gray-700 pt-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Analyze the whole song, then review and clean it. Cleaning
                produces a new version — the version you start from is never
                overwritten, so you can re-clean an already-cleaned version
                with different options.
              </p>

              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                {analyzing ? 'Analyzing...' : 'Analyze'}
              </button>

              {analysis && (
                <div className="mt-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                    Detected issues
                  </h3>
                  {analysis.status === 'error' ? (
                    <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
                      {analysis.error}
                    </div>
                  ) : (
                    <>
                      <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
                        {analysis.summary}
                      </p>
                      <ul className="text-sm text-gray-600 dark:text-gray-400 list-disc list-inside space-y-1">
                        {(analysis.processing_order || [])
                          .filter((s: string | null) => s)
                          .map((s: string) => (
                            <li key={s}>{s}</li>
                          ))}
                      </ul>
                    </>
                  )}
                </div>
              )}

              {analysisOk && (
                <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-6">
                  <div className="mb-4">
                    <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Intensity
                      <InfoTip text={INTENSITY_HELP} label="Intensity" />
                    </label>
                    <select
                      value={intensity}
                      onChange={(e) => setIntensity(e.target.value as Intensity)}
                      className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
                    >
                      <option value="gentle">Gentle</option>
                      <option value="moderate">Moderate</option>
                      <option value="aggressive">Aggressive</option>
                    </select>
                  </div>

                  <div className="mb-4">
                    <p className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Steps
                    </p>
                    <div className="space-y-2">
                      {STEPS.map((step) => (
                        <label
                          key={step.key}
                          className="flex items-center gap-2 text-sm text-gray-800 dark:text-gray-200"
                        >
                          <input
                            type="checkbox"
                            checked={!!stepEnabled[step.key]}
                            onChange={() => toggleStep(step.key)}
                            className="h-4 w-4"
                          />
                          {step.label}
                          <InfoTip text={step.help} label={step.label} />
                        </label>
                      ))}
                    </div>
                  </div>

                  <button
                    onClick={handleClean}
                    disabled={cleaning}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {cleaning ? 'Cleaning...' : 'Clean to new version'}
                  </button>
                </div>
              )}

              {cleanResult && (
                <div className="mt-6">
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                    Result
                  </h3>
                  {cleanResult.status === 'error' ? (
                    <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
                      <p className="font-semibold">Failed</p>
                      <p className="mt-1">{cleanResult.error}</p>
                    </div>
                  ) : (
                    <div className="p-4 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 rounded-lg">
                      <p className="font-semibold">
                        Success — {cleanResult.total_steps} step(s) applied.
                        Saved as a new version below.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-5 border-t border-gray-200 dark:border-gray-700 pt-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Tool
                  </label>
                  <select
                    value={tool}
                    onChange={(e) => {
                      setTool(e.target.value as ToolKey);
                      setPreviewPath(null);
                      setMessage(null);
                    }}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
                  >
                    {TOOLS.map((t) => (
                      <option key={t.key} value={t.key}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {TOOLS.find((t) => t.key === tool)?.help}
                  </p>
                </div>

                {tool !== 'trim' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                      Strength (wet/dry): {strength.toFixed(2)}
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={strength}
                      onChange={(e) => setStrength(Number(e.target.value))}
                      className="w-full"
                    />
                  </div>
                )}
              </div>

              {/* Tool-specific controls */}
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {tool === 'pitch' && (
                  <>
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      Key override (optional)
                      <input
                        type="text"
                        placeholder="e.g. A minor"
                        value={params.key ?? ''}
                        onChange={(e) => setParam({ key: e.target.value || undefined })}
                        className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 mt-6">
                      <input
                        type="checkbox"
                        checked={!!params.chromatic}
                        onChange={(e) => setParam({ chromatic: e.target.checked })}
                      />
                      Chromatic (snap to nearest semitone)
                    </label>
                  </>
                )}

                {tool === 'tempo' && (
                  <label className="text-sm text-gray-700 dark:text-gray-300">
                    Target BPM (optional)
                    <input
                      type="number"
                      min={40}
                      max={240}
                      value={params.target_bpm ?? ''}
                      onChange={(e) =>
                        setParam({
                          target_bpm: e.target.value ? Number(e.target.value) : undefined,
                        })
                      }
                      className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    />
                  </label>
                )}

                {tool === 'noise_reduction' && (
                  <>
                    <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                      <input
                        type="checkbox"
                        checked={!!params.non_stationary}
                        onChange={(e) => setParam({ non_stationary: e.target.checked })}
                      />
                      Non-stationary (adaptive) reduction
                    </label>
                    <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                      <input
                        type="checkbox"
                        checked={!!params.noise_from_selection}
                        disabled={!hasRegion}
                        onChange={(e) => setParam({ noise_from_selection: e.target.checked })}
                      />
                      Use selection as the noise profile (denoise whole file)
                    </label>
                  </>
                )}

                {tool === 'eq' && (
                  <>
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      High-pass (Hz)
                      <input
                        type="number"
                        value={params.high_pass_freq ?? ''}
                        onChange={(e) =>
                          setParam({ high_pass_freq: e.target.value ? Number(e.target.value) : undefined })
                        }
                        className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </label>
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      Low-pass (Hz)
                      <input
                        type="number"
                        value={params.low_pass_freq ?? ''}
                        onChange={(e) =>
                          setParam({ low_pass_freq: e.target.value ? Number(e.target.value) : undefined })
                        }
                        className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </label>
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      Boost frequency (Hz)
                      <input
                        type="number"
                        value={params.boost_freq ?? ''}
                        onChange={(e) =>
                          setParam({ boost_freq: e.target.value ? Number(e.target.value) : undefined })
                        }
                        className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </label>
                    <label className="text-sm text-gray-700 dark:text-gray-300">
                      Boost amount (dB)
                      <input
                        type="number"
                        value={params.boost_db ?? ''}
                        onChange={(e) =>
                          setParam({ boost_db: e.target.value ? Number(e.target.value) : undefined })
                        }
                        className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </label>
                  </>
                )}
              </div>

              {needsRegion && !hasRegion && (
                <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                  This tool needs a region — drag on the waveform to select one.
                </p>
              )}

              <div className="flex flex-wrap items-center gap-3 mt-4">
                <button
                  onClick={handlePreview}
                  disabled={!canRunRegionTool}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {busy === 'preview' ? 'Previewing…' : 'Preview'}
                </button>
                <button
                  onClick={handleApply}
                  disabled={!canRunRegionTool}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {busy === 'apply' ? 'Applying…' : 'Apply as new version'}
                </button>
              </div>

              {message && (
                <p className="mt-3 text-sm text-gray-700 dark:text-gray-300">{message}</p>
              )}

              {previewPath && (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                      Original
                    </p>
                    {sourceAudioUrl && (
                      <audio controls preload="none" src={sourceAudioUrl} className="h-9 w-full" />
                    )}
                  </div>
                  <div>
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                      Preview (processed)
                    </p>
                    <audio
                      controls
                      preload="none"
                      src={`/api/produce/clean/preview?path=${encodeURIComponent(previewPath)}`}
                      className="h-9 w-full"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Per-stem rows (only render once stems exist for the song). */}
          <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
              Stems
            </h3>
            <StemMixer songId={songId} onApplied={onApplied} />
          </div>
        </>
      )}
    </div>
  );
}
