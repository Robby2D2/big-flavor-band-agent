'use client';

import { useState, useEffect } from 'react';
import Header from '@/components/Header';

interface CatalogSong {
  id: number;
  title: string;
}

type Intensity = 'gentle' | 'moderate' | 'aggressive';

// The cleanup steps the editor can toggle, in processing order. Keys match the
// backend steps_override map (trim / noise_reduction / eq / normalize / master).
const STEPS: { key: string; label: string }[] = [
  { key: 'trim', label: 'Trim non-musical content' },
  { key: 'noise_reduction', label: 'Reduce noise' },
  { key: 'eq', label: 'Apply EQ corrections' },
  { key: 'normalize', label: 'Normalize' },
  { key: 'master', label: 'Master' },
];

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

  useEffect(() => {
    loadSongs();
  }, []);

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
                setSelectedSongId(e.target.value ? Number(e.target.value) : null);
                setAnalysis(null);
                setCleanResult(null);
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
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Intensity
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
                    <pre className="mt-2 text-xs overflow-auto max-h-72">
                      {JSON.stringify(cleanResult.steps_applied, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
