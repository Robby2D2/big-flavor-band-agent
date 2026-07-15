'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import MultitrackEditor from '@/components/produce/MultitrackEditor';

interface CatalogSong {
  id: number;
  title: string;
}

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
    } catch (err: any) {
      setVersionsError(err.message);
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
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

        {/* Audio processing (unified whole-song + region editor, issue #77) */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            Audio processing
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Pick a starting version, then either clean the whole song
            (analyze → recommended steps/intensity → clean) or drag-select a
            region on the waveform and run a tool with Preview/Apply.
            Cleaning/Applying always produces a new version below — the
            version you start from is never overwritten. If the song has been
            separated into stems, each part appears with its own mute / solo
            / gain.
          </p>
          <MultitrackEditor
            songId={songId}
            versions={versions}
            onApplied={loadVersions}
          />
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
