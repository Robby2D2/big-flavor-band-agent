'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';

interface CatalogSong {
  id: number;
  title: string;
}

type Intensity = 'gentle' | 'moderate' | 'aggressive';

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

// The cleanup steps the editor can toggle, in processing order. Keys match the
// backend steps_override map (trim / noise_reduction / eq / normalize / master).
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

export default function ProduceSongPage({
  params,
}: {
  params: Promise<{ songId: string }>;
}) {
  const { songId: songIdParam } = use(params);
  const songId = Number(songIdParam);

  const [song, setSong] = useState<CatalogSong | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [versions, setVersions] = useState<SongVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionBusyId, setVersionBusyId] = useState<number | null>(null);

  // Version-level analyze + clean. A clean starts from `sourceVersionId` and
  // produces a NEW version — the source version is never overwritten.
  const [sourceVersionId, setSourceVersionId] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [intensity, setIntensity] = useState<Intensity>('moderate');
  const [stepEnabled, setStepEnabled] = useState<Record<string, boolean>>({});
  const [cleanResult, setCleanResult] = useState<any>(null);
  const [cleaning, setCleaning] = useState(false);

  useEffect(() => {
    if (Number.isNaN(songId)) {
      setError('Invalid song id.');
      setLoading(false);
      return;
    }
    loadSong();
    loadVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [songId]);

  const loadSong = async () => {
    try {
      const response = await fetch(`/api/produce/songs/${songId}`);
      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        setLoading(false);
        return;
      }
      if (!response.ok) {
        throw new Error('Failed to load song');
      }
      const data = await response.json();
      setSong(data.song);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadVersions = async () => {
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/songs/${songId}/versions`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to load versions');
      }
      const list: SongVersion[] = data.versions || [];
      setVersions(list);
      // Default the clean source to the published version, else the first one.
      setSourceVersionId((prev) => {
        if (prev != null && list.some((v) => v.id === prev)) return prev;
        const published = list.find((v) => v.is_published);
        return published?.id ?? list[0]?.id ?? null;
      });
    } catch (err: any) {
      setVersionsError(err.message);
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  };

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
      seedStepsFromAnalysis(data.result);
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
        loadVersions();
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

  const handleSetDefault = async (versionId: number) => {
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}/default`, {
        method: 'POST',
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to set default');
      }
      await loadVersions();
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleRenameVersion = async (versionId: number, currentName: string) => {
    const next = window.prompt('Rename version', currentName);
    if (next == null) return;
    const name = next.trim();
    if (!name || name === currentName) return;
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to rename');
      }
      await loadVersions();
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleDeleteVersion = async (versionId: number, name: string) => {
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
      await loadVersions();
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
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading song...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
          <div className="text-red-600 dark:text-red-400 text-center">
            <h2 className="text-2xl font-bold mb-2">Unable to load song</h2>
            <p className="text-gray-600 dark:text-gray-400">{error}</p>
            <Link
              href="/produce"
              className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Back to catalog
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const analysisOk = analysis && analysis.status === 'success';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header title="Produce" subtitle={song?.title ?? 'Song detail'} />

      <main className="container mx-auto px-4 py-8">
        <Link
          href="/produce"
          className="inline-block mb-4 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          ← Back to catalog
        </Link>

        <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-6">
          {song?.title}
        </h1>

        {/* Analyze + clean (version-level) */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
            Analyze and clean a version
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Pick a starting version, then analyze and clean it. Cleaning produces a
            new version — the version you start from is never overwritten, so you can
            re-clean an already-cleaned version with different options.
          </p>

          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Starting version
            </label>
            <select
              value={sourceVersionId ?? ''}
              onChange={(e) => {
                setSourceVersionId(e.target.value ? Number(e.target.value) : null);
                setAnalysis(null);
                setCleanResult(null);
              }}
              disabled={versions.length === 0}
              className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              {versions.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                  {v.is_published ? ' (default)' : ''}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={sourceVersionId == null || analyzing}
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
                    Success — {cleanResult.total_steps} step(s) applied. Saved as a new
                    version below.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Manage versions */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Manage versions
            </h2>
            <button
              onClick={loadVersions}
              disabled={versionsLoading}
              className="text-sm px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              {versionsLoading ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            The default version is what plays everywhere — radio, search and preview,
            and downloads. The original is always kept until you delete it.
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
                        {v.created_at ? new Date(v.created_at).toLocaleString() : '—'}
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
      </main>
    </div>
  );
}
