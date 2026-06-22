'use client';

import { useState, useEffect } from 'react';
import Header from '@/components/Header';

interface CatalogSong {
  id: number;
  title: string;
}

interface SongVersion {
  id: number;
  label: string;
  is_published: boolean;
  metrics: Record<string, any> | null;
  created_at: string | null;
}

interface VersionMetrics {
  duration_seconds: number | null;
  peak_db: number | null;
  integrated_lufs_estimate: number | null;
}

interface CleanupStep {
  step: string;
  [key: string]: any;
}

interface CleanupDiff {
  before: VersionMetrics | null;
  after: VersionMetrics | null;
  steps_applied: CleanupStep[];
  aggressiveness: string | null;
  noise_reduction_db: number | null;
  analysis_summary: string | null;
}

interface CleanResult {
  song_id: number;
  candidate_path: string;
  diff: CleanupDiff;
}

const AGGRESSIVENESS = ['gentle', 'moderate', 'aggressive'];

function formatMetric(value: number | null | undefined, suffix: string): string {
  return value === null || value === undefined ? '—' : `${value}${suffix}`;
}

export default function ProducePage() {
  const [songs, setSongs] = useState<CatalogSong[]>([]);
  const [selectedSong, setSelectedSong] = useState<number | null>(null);
  const [aggressiveness, setAggressiveness] = useState('moderate');
  const [versions, setVersions] = useState<SongVersion[]>([]);
  const [candidate, setCandidate] = useState<CleanResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [cleaning, setCleaning] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSongs();
  }, []);

  const loadSongs = async () => {
    try {
      const res = await fetch('/api/produce/songs');
      if (res.status === 403) {
        setError('Access denied. Editor role required.');
        setLoading(false);
        return;
      }
      if (!res.ok) throw new Error('Failed to load songs');
      const data = await res.json();
      setSongs(data.songs || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadVersions = async (songId: number) => {
    const res = await fetch(`/api/produce/songs/${songId}/versions`);
    if (!res.ok) throw new Error('Failed to load versions');
    const data = await res.json();
    setVersions(data.versions || []);
  };

  const selectSong = async (songId: number) => {
    setSelectedSong(songId);
    setCandidate(null);
    setError(null);
    try {
      await loadVersions(songId);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const runCleanup = async () => {
    if (selectedSong === null) return;
    setCleaning(true);
    setCandidate(null);
    setError(null);
    try {
      const res = await fetch('/api/produce/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: selectedSong, aggressiveness }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Cleanup failed');
      setCandidate(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setCleaning(false);
    }
  };

  const approve = async () => {
    if (!candidate || selectedSong === null) return;
    setWorking(true);
    setError(null);
    try {
      const res = await fetch('/api/produce/approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: selectedSong,
          candidate_path: candidate.candidate_path,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Approve failed');
      setCandidate(null);
      await loadVersions(selectedSong);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setWorking(false);
    }
  };

  const discard = async () => {
    if (!candidate) return;
    setWorking(true);
    setError(null);
    try {
      const res = await fetch('/api/produce/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_path: candidate.candidate_path }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Discard failed');
      }
      setCandidate(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setWorking(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading...</p>
        </div>
      </div>
    );
  }

  if (error && songs.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 text-center">
          <h2 className="text-2xl font-bold mb-2 text-red-600 dark:text-red-400">
            Access Denied
          </h2>
          <p className="text-gray-600 dark:text-gray-400">{error}</p>
          <a
            href="/admin"
            className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Back to Admin
          </a>
        </div>
      </div>
    );
  }

  const diff = candidate?.diff;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header
        title="Producer Studio"
        subtitle="Audition, diff, and publish cleaned audio versions"
      />

      <main className="container mx-auto px-4 py-8 space-y-6">
        {error && songs.length > 0 && (
          <div className="bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-700 rounded-lg p-4 text-sm text-red-800 dark:text-red-200">
            {error}
          </div>
        )}

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            1. Pick a song
          </h2>
          <div className="flex flex-wrap items-center gap-4">
            <select
              value={selectedSong ?? ''}
              onChange={(e) => selectSong(Number(e.target.value))}
              className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              <option value="" disabled>
                Select a song…
              </option>
              {songs.map((song) => (
                <option key={song.id} value={song.id}>
                  {song.title}
                </option>
              ))}
            </select>

            <select
              value={aggressiveness}
              onChange={(e) => setAggressiveness(e.target.value)}
              className="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
            >
              {AGGRESSIVENESS.map((level) => (
                <option key={level} value={level}>
                  {level}
                </option>
              ))}
            </select>

            <button
              onClick={runCleanup}
              disabled={selectedSong === null || cleaning}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {cleaning ? 'Cleaning…' : 'Run auto-clean'}
            </button>
          </div>
        </div>

        {selectedSong !== null && versions.length > 0 && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Versions
            </h2>
            <div className="space-y-3">
              {versions.map((version) => (
                <div
                  key={version.id}
                  className="flex items-center justify-between gap-4 border border-gray-200 dark:border-gray-700 rounded-lg p-3"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white capitalize">
                      {version.label}
                    </span>
                    {version.is_published && (
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                        Published
                      </span>
                    )}
                  </div>
                  <audio
                    controls
                    preload="none"
                    src={`/api/produce/versions/${version.id}/audio`}
                    className="h-8"
                  />
                </div>
              ))}
            </div>
          </div>
        )}

        {diff && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              2. Audition the cleaned candidate
            </h2>

            <div className="mb-4">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
                Cleaned candidate preview
              </p>
              <audio
                controls
                preload="none"
                src={`/api/produce/clean/preview?path=${encodeURIComponent(
                  candidate!.candidate_path
                )}`}
                className="h-8"
              />
            </div>

            <table className="w-full text-sm mb-4">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400">
                  <th className="py-2">Metric</th>
                  <th className="py-2">Before (original)</th>
                  <th className="py-2">After (cleaned)</th>
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-white">
                <tr className="border-t border-gray-200 dark:border-gray-700">
                  <td className="py-2">Integrated LUFS (est.)</td>
                  <td>{formatMetric(diff.before?.integrated_lufs_estimate, ' LUFS')}</td>
                  <td>{formatMetric(diff.after?.integrated_lufs_estimate, ' LUFS')}</td>
                </tr>
                <tr className="border-t border-gray-200 dark:border-gray-700">
                  <td className="py-2">Peak</td>
                  <td>{formatMetric(diff.before?.peak_db, ' dB')}</td>
                  <td>{formatMetric(diff.after?.peak_db, ' dB')}</td>
                </tr>
                <tr className="border-t border-gray-200 dark:border-gray-700">
                  <td className="py-2">Duration</td>
                  <td>{formatMetric(diff.before?.duration_seconds, ' s')}</td>
                  <td>{formatMetric(diff.after?.duration_seconds, ' s')}</td>
                </tr>
              </tbody>
            </table>

            <div className="text-sm text-gray-700 dark:text-gray-300 space-y-1 mb-4">
              <p>
                <strong>Aggressiveness:</strong> {diff.aggressiveness ?? '—'}
              </p>
              <p>
                <strong>Noise reduction:</strong>{' '}
                {formatMetric(diff.noise_reduction_db, ' dB')}
              </p>
              <p>
                <strong>Steps applied:</strong>{' '}
                {diff.steps_applied.length > 0
                  ? diff.steps_applied.map((s) => s.step).join(' → ')
                  : 'none'}
              </p>
              {diff.analysis_summary && (
                <p>
                  <strong>Summary:</strong> {diff.analysis_summary}
                </p>
              )}
            </div>

            <div className="flex gap-3">
              <button
                onClick={approve}
                disabled={working}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                {working ? 'Working…' : 'Approve & publish'}
              </button>
              <button
                onClick={discard}
                disabled={working}
                className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
              >
                Discard
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
