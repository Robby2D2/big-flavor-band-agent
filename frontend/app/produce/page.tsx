'use client';

import { useState, useEffect, useRef } from 'react';
import Header from '@/components/Header';

interface CatalogSong {
  id: number;
  title: string;
}

type Intensity = 'gentle' | 'moderate' | 'aggressive';
type BatchSelection = 'all' | 'not_cleaned';

interface SongVersion {
  id: number;
  name: string;
  label: string;
  is_published: boolean;
  steps_applied: { step: string }[] | null;
  aggressiveness: string | null;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  created_at: string | null;
}

interface BatchTrackResult {
  song_id: number;
  title: string;
  outcome: 'succeeded' | 'skipped' | 'failed';
  reason: string | null;
}

interface BatchStatus {
  status: 'idle' | 'running' | 'completed' | 'failed';
  selection?: BatchSelection;
  total?: number;
  completed?: number;
  succeeded?: number;
  skipped?: number;
  failed?: number;
  results?: BatchTrackResult[];
  error?: string | null;
}

// The cleanup steps the editor can toggle, in processing order. Keys match the
// backend steps_override map (trim / noise_reduction / eq / normalize / master).
// `help` copy reflects what auto_clean_recording() in big_flavor_mcp.py actually
// does for each step — keep it in sync if the pipeline changes.
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

// Discoverable inline help: an info icon with a hover/focus tooltip. Uses the
// native `title` attribute (the same tooltip pattern used elsewhere in the app),
// so it needs no extra layout and reads correctly in light and dark mode.
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

export default function ProducePage() {
  const [songs, setSongs] = useState<CatalogSong[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedSongId, setSelectedSongId] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const [intensity, setIntensity] = useState<Intensity>('moderate');
  const [stepEnabled, setStepEnabled] = useState<Record<string, boolean>>({});

  const [cleanResult, setCleanResult] = useState<any>(null);
  const [cleaning, setCleaning] = useState(false);

  // Versions management (issue #43).
  const [versions, setVersions] = useState<SongVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionBusyId, setVersionBusyId] = useState<number | null>(null);

  // Catalog-wide batch clean (issue #29).
  const [batchSelection, setBatchSelection] = useState<BatchSelection>('not_cleaned');
  const [batchForceReclean, setBatchForceReclean] = useState(false);
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [batchStarting, setBatchStarting] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);
  const batchPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    loadSongs();
    refreshBatchStatus();
    return () => stopBatchPolling();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopBatchPolling = () => {
    if (batchPollRef.current) {
      clearInterval(batchPollRef.current);
      batchPollRef.current = null;
    }
  };

  const refreshBatchStatus = async () => {
    try {
      const response = await fetch('/api/produce/batch/status');
      if (!response.ok) return;
      const data: BatchStatus = await response.json();
      setBatchStatus(data);
      if (data.status === 'running') {
        startBatchPolling();
      } else {
        stopBatchPolling();
      }
    } catch {
      // status polling is best-effort; ignore transient errors
    }
  };

  const startBatchPolling = () => {
    if (batchPollRef.current) return;
    batchPollRef.current = setInterval(refreshBatchStatus, 2000);
  };

  const handleStartBatch = async () => {
    setBatchStarting(true);
    setBatchError(null);
    try {
      const response = await fetch('/api/produce/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          selection: batchSelection,
          aggressiveness: intensity,
          force_reclean_all: batchForceReclean,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to start batch');
      }
      setBatchStatus(data);
      startBatchPolling();
    } catch (err: any) {
      setBatchError(err.message);
    } finally {
      setBatchStarting(false);
    }
  };

  const loadSongs = async () => {
    try {
      const response = await fetch('/api/produce/songs');
      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        setLoading(false);
        return;
      }
      if (!response.ok) {
        throw new Error('Failed to load songs');
      }
      const data = await response.json();
      setSongs(data.songs || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Seed the step toggles from the analysis recommendations so the editor starts
  // from what the engine recommends, then can adjust.
  const seedStepsFromAnalysis = (result: any) => {
    const recs = result?.recommendations;
    if (!recs) return;
    setStepEnabled({
      trim: !!recs.trim?.recommended,
      noise_reduction: !!recs.noise_reduction?.recommended,
      eq: !!recs.eq?.recommended,
      normalize: recs.normalization?.recommended ?? true,
      master: recs.mastering?.recommended ?? true,
    });
  };

  const handleAnalyze = async () => {
    if (selectedSongId == null) return;
    setAnalyzing(true);
    setAnalysis(null);
    setCleanResult(null);
    try {
      const response = await fetch('/api/produce/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: selectedSongId }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Analysis failed');
      }
      setAnalysis(data.result);
      seedStepsFromAnalysis(data.result);
    } catch (err: any) {
      setAnalysis({ status: 'error', error: err.message });
    } finally {
      setAnalyzing(false);
    }
  };

  const handleAutoClean = async () => {
    if (selectedSongId == null) return;
    setCleaning(true);
    setCleanResult(null);
    try {
      const response = await fetch('/api/produce/auto-clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: selectedSongId,
          aggressiveness: intensity,
          steps_override: stepEnabled,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Auto-clean failed');
      }
      setCleanResult(data.result);
    } catch (err: any) {
      setCleanResult({ status: 'error', error: err.message });
    } finally {
      setCleaning(false);
    }
  };

  const toggleStep = (key: string) => {
    setStepEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  // --- Versions management (issue #43) ---

  const loadVersions = async (songId: number) => {
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/songs/${songId}/versions`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to load versions');
      }
      setVersions(data.versions || []);
    } catch (err: any) {
      setVersionsError(err.message);
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  };

  const handleSetDefault = async (versionId: number) => {
    if (selectedSongId == null) return;
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(
        `/api/produce/versions/${versionId}/default`,
        { method: 'POST' }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to set default');
      }
      await loadVersions(selectedSongId);
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleRenameVersion = async (versionId: number, currentName: string) => {
    if (selectedSongId == null) return;
    const next = window.prompt('Rename version', currentName);
    if (next == null) return;
    const name = next.trim();
    if (!name || name === currentName) return;
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(
        `/api/produce/versions/${versionId}/rename`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        }
      );
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to rename');
      }
      await loadVersions(selectedSongId);
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleDeleteVersion = async (versionId: number, name: string) => {
    if (selectedSongId == null) return;
    if (!window.confirm(`Delete version "${name}"? This removes its audio file.`)) {
      return;
    }
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to delete');
      }
      await loadVersions(selectedSongId);
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const formatBytes = (bytes: number | null): string => {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} B`;
    const units = ['KB', 'MB', 'GB'];
    let value = bytes / 1024;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value.toFixed(1)} ${units[unit]}`;
  };

  const formatDuration = (seconds: number | null): string => {
    if (seconds == null) return '—';
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading catalog...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
          <div className="text-red-600 dark:text-red-400 text-center">
            <h2 className="text-2xl font-bold mb-2">Access Denied</h2>
            <p className="text-gray-600 dark:text-gray-400">{error}</p>
            <a
              href="/"
              className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Back to Home
            </a>
          </div>
        </div>
      </div>
    );
  }

  const analysisOk = analysis && analysis.status === 'success';
  // Force reclean is a no-op under the not-cleaned selection (already-cleaned songs
  // are excluded before the force check), so present it as non-actionable there.
  const forceRecleanDisabled =
    batchStatus?.status === 'running' || batchSelection === 'not_cleaned';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header
        title="Produce"
        subtitle="Analyze and auto-clean catalog audio"
      />

      <main className="container mx-auto px-4 py-8">
        <div className="grid md:grid-cols-2 gap-6">
          {/* Select + Analyze */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              1. Select a song
            </h2>
            <select
              value={selectedSongId ?? ''}
              onChange={(e) => {
                const nextId = e.target.value ? Number(e.target.value) : null;
                setSelectedSongId(nextId);
                setAnalysis(null);
                setCleanResult(null);
                setVersions([]);
                setVersionsError(null);
                if (nextId != null) {
                  loadVersions(nextId);
                }
              }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
            >
              <option value="">-- Choose a catalog song --</option>
              {songs.map((song) => (
                <option key={song.id} value={song.id}>
                  {song.title}
                </option>
              ))}
            </select>

            <button
              onClick={handleAnalyze}
              disabled={selectedSongId == null || analyzing}
              className="w-full mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
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
          </div>

          {/* Configure + Run */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              2. Configure and clean
            </h2>

            {!analysisOk ? (
              <p className="text-gray-500 dark:text-gray-400">
                Analyze a song to configure the cleanup steps.
              </p>
            ) : (
              <>
                <div className="mb-4">
                  <label className="flex items-center gap-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Intensity
                    <InfoTip text={INTENSITY_HELP} label="Intensity" />
                  </label>
                  <select
                    value={intensity}
                    onChange={(e) => setIntensity(e.target.value as Intensity)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
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
                  onClick={handleAutoClean}
                  disabled={cleaning}
                  className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {cleaning ? 'Cleaning...' : 'Auto-clean'}
                </button>
              </>
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
                      Success — {cleanResult.total_steps} step(s) applied
                    </p>
                    <p className="mt-1 text-sm break-all">
                      Cleaned output: {cleanResult.output_file}
                    </p>

                    <div className="mt-3 grid grid-cols-2 gap-3">
                      <div>
                        <p className="text-xs font-medium mb-1">Before (original)</p>
                        <audio
                          controls
                          preload="none"
                          src={`/api/audio/${selectedSongId}`}
                          className="w-full h-8"
                        />
                      </div>
                      <div>
                        <p className="text-xs font-medium mb-1">After (cleaned)</p>
                        <audio
                          controls
                          preload="none"
                          src={`/api/produce/clean/preview?path=${encodeURIComponent(
                            cleanResult.output_file
                          )}`}
                          className="w-full h-8"
                        />
                      </div>
                    </div>

                    <pre className="mt-3 text-xs overflow-auto max-h-72">
                      {JSON.stringify(cleanResult.steps_applied, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Manage versions (issue #43) */}
        {selectedSongId != null && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mt-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                Manage versions
              </h2>
              <button
                onClick={() => loadVersions(selectedSongId)}
                disabled={versionsLoading}
                className="text-sm px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
              >
                {versionsLoading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              The default version is what plays everywhere — radio, search and
              preview, and downloads. The original is always kept until you delete
              it.
            </p>

            {versionsError && (
              <div className="p-3 mb-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
                {versionsError}
              </div>
            )}

            {versions.length === 0 && !versionsLoading ? (
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                No versions yet for this song.
              </p>
            ) : (
              <div className="overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-500 dark:text-gray-400">
                    <tr>
                      <th className="py-2 px-3">Version</th>
                      <th className="py-2 px-3">Steps</th>
                      <th className="py-2 px-3">Intensity</th>
                      <th className="py-2 px-3">Duration</th>
                      <th className="py-2 px-3">Size</th>
                      <th className="py-2 px-3">Produced</th>
                      <th className="py-2 px-3">Audition</th>
                      <th className="py-2 px-3">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="text-gray-900 dark:text-white">
                    {versions.map((v) => (
                      <tr
                        key={v.id}
                        className="border-t border-gray-200 dark:border-gray-700 align-middle"
                      >
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{v.name}</span>
                            {v.is_published && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200">
                                Default
                              </span>
                            )}
                            {v.label === 'original' && (
                              <span className="text-xs text-gray-400 dark:text-gray-500">
                                original
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                          {v.steps_applied && v.steps_applied.length > 0
                            ? v.steps_applied.map((s) => s.step).join(', ')
                            : '—'}
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400 capitalize">
                          {v.aggressiveness ?? '—'}
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                          {formatDuration(v.duration_seconds)}
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                          {formatBytes(v.file_size_bytes)}
                        </td>
                        <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                          {v.created_at
                            ? new Date(v.created_at).toLocaleString()
                            : '—'}
                        </td>
                        <td className="py-2 px-3">
                          <audio
                            controls
                            preload="none"
                            src={`/api/produce/versions/${v.id}/audio`}
                            className="h-8 w-44"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              onClick={() => handleSetDefault(v.id)}
                              disabled={v.is_published || versionBusyId === v.id}
                              className="text-xs px-2 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
                            >
                              Set default
                            </button>
                            <button
                              onClick={() => handleRenameVersion(v.id, v.name)}
                              disabled={versionBusyId === v.id}
                              className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                            >
                              Rename
                            </button>
                            <button
                              onClick={() => handleDeleteVersion(v.id, v.name)}
                              disabled={versionBusyId === v.id || versions.length <= 1}
                              className="text-xs px-2 py-1 border border-red-300 dark:border-red-700 rounded text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Catalog-wide batch clean (issue #29) */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mt-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Clean catalog (batch)
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Run auto-clean over the whole catalog hands-off. Each result is published
            as a new cleaned version — originals are never overwritten. Uses the
            intensity selected above.
          </p>

          <div className="flex flex-wrap items-end gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Songs
              </label>
              <select
                value={batchSelection}
                onChange={(e) => {
                  const next = e.target.value as BatchSelection;
                  setBatchSelection(next);
                  // Force reclean only applies to the all-songs selection; clear it
                  // when switching to not-cleaned so it can't appear checked-but-inert.
                  if (next === 'not_cleaned') setBatchForceReclean(false);
                }}
                disabled={batchStatus?.status === 'running'}
                className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
              >
                <option value="not_cleaned">Not yet cleaned</option>
                <option value="all">All songs</option>
              </select>
            </div>

            <div className="mb-2">
              <label
                className={`flex items-center gap-2 text-sm ${
                  forceRecleanDisabled
                    ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed'
                    : 'text-gray-800 dark:text-gray-200'
                }`}
              >
                <input
                  type="checkbox"
                  checked={batchForceReclean}
                  onChange={(e) => setBatchForceReclean(e.target.checked)}
                  disabled={forceRecleanDisabled}
                  className="h-4 w-4 disabled:cursor-not-allowed"
                />
                Force re-clean all (reprocess already-cleaned songs)
              </label>
              {batchSelection === 'not_cleaned' && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  Force reclean only applies to the <span className="font-medium">All songs</span> selection.
                </p>
              )}
            </div>

            <button
              onClick={handleStartBatch}
              disabled={batchStarting || batchStatus?.status === 'running'}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {batchStatus?.status === 'running'
                ? 'Running...'
                : batchStarting
                ? 'Starting...'
                : 'Start batch'}
            </button>
          </div>

          {batchError && (
            <div className="p-3 mb-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
              {batchError}
            </div>
          )}

          {batchStatus && batchStatus.status !== 'idle' && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-sm text-gray-700 dark:text-gray-300 mb-2">
                <span className="font-medium capitalize">{batchStatus.status}</span>
                <span>
                  {batchStatus.completed ?? 0} / {batchStatus.total ?? 0} processed
                </span>
              </div>

              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-3">
                <div
                  className="bg-purple-600 h-2 rounded-full transition-all"
                  style={{
                    width: `${
                      batchStatus.total
                        ? Math.round(
                            ((batchStatus.completed ?? 0) / batchStatus.total) * 100
                          )
                        : 0
                    }%`,
                  }}
                />
              </div>

              <div className="flex gap-4 text-sm text-gray-600 dark:text-gray-400 mb-3">
                <span>✓ {batchStatus.succeeded ?? 0} succeeded</span>
                <span>↷ {batchStatus.skipped ?? 0} skipped</span>
                <span>✕ {batchStatus.failed ?? 0} failed</span>
              </div>

              {batchStatus.error && (
                <div className="p-3 mb-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
                  {batchStatus.error}
                </div>
              )}

              {batchStatus.results && batchStatus.results.length > 0 && (
                <div className="max-h-72 overflow-auto border border-gray-200 dark:border-gray-700 rounded-lg">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-500 dark:text-gray-400 sticky top-0">
                      <tr>
                        <th className="py-2 px-3">Song</th>
                        <th className="py-2 px-3">Outcome</th>
                        <th className="py-2 px-3">Reason</th>
                      </tr>
                    </thead>
                    <tbody className="text-gray-900 dark:text-white">
                      {batchStatus.results.map((r) => (
                        <tr
                          key={r.song_id}
                          className="border-t border-gray-200 dark:border-gray-700"
                        >
                          <td className="py-2 px-3">{r.title}</td>
                          <td className="py-2 px-3 capitalize">{r.outcome}</td>
                          <td className="py-2 px-3 text-gray-500 dark:text-gray-400">
                            {r.reason ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
