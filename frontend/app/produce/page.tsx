'use client';

import { useState, useEffect, useMemo } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';

interface CatalogSong {
  id: number;
  title: string;
  genre: string | null;
  tempo_bpm: number | null;
  duration_seconds: number | null;
  cleaned: boolean;
}

type Intensity = 'gentle' | 'moderate' | 'aggressive';

type CleanOutcome = 'succeeded' | 'skipped' | 'failed';

interface CleanResultRow {
  song_id: number;
  title: string;
  outcome: CleanOutcome;
  reason: string | null;
}

// Sortable/filterable columns of the catalog table. `value` pulls the raw cell
// value off a song; `display` renders it. Filtering is a case-insensitive match
// over `display`, so what a producer sees is what they filter on.
type ColumnKey = 'title' | 'genre' | 'tempo_bpm' | 'duration_seconds' | 'cleaned';

const formatDuration = (seconds: number | null): string => {
  if (seconds == null) return '';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
};

const COLUMNS: {
  key: ColumnKey;
  label: string;
  value: (s: CatalogSong) => string | number | null;
  display: (s: CatalogSong) => string;
}[] = [
  { key: 'title', label: 'Title', value: (s) => s.title, display: (s) => s.title },
  { key: 'genre', label: 'Genre', value: (s) => s.genre, display: (s) => s.genre ?? '' },
  {
    key: 'tempo_bpm',
    label: 'Tempo',
    value: (s) => s.tempo_bpm,
    display: (s) => (s.tempo_bpm == null ? '' : Math.round(s.tempo_bpm).toString()),
  },
  {
    key: 'duration_seconds',
    label: 'Duration',
    value: (s) => s.duration_seconds,
    display: (s) => formatDuration(s.duration_seconds),
  },
  {
    key: 'cleaned',
    label: 'Cleaned',
    value: (s) => (s.cleaned ? 1 : 0),
    display: (s) => (s.cleaned ? 'Yes' : 'No'),
  },
];

export default function ProducePage() {
  const [songs, setSongs] = useState<CatalogSong[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [filters, setFilters] = useState<Record<ColumnKey, string>>({
    title: '',
    genre: '',
    tempo_bpm: '',
    duration_seconds: '',
    cleaned: '',
  });
  const [sortKey, setSortKey] = useState<ColumnKey>('title');
  const [sortAsc, setSortAsc] = useState(true);

  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  const [intensity, setIntensity] = useState<Intensity>('moderate');
  const [cleaning, setCleaning] = useState(false);
  const [cleanProgress, setCleanProgress] = useState<{ done: number; total: number } | null>(null);
  const [cleanResults, setCleanResults] = useState<CleanResultRow[]>([]);
  const [cleanError, setCleanError] = useState<string | null>(null);

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

  const visibleSongs = useMemo(() => {
    const filtered = songs.filter((song) =>
      COLUMNS.every((col) => {
        const term = filters[col.key].trim().toLowerCase();
        if (!term) return true;
        return col.display(song).toLowerCase().includes(term);
      })
    );

    const column = COLUMNS.find((c) => c.key === sortKey)!;
    const sorted = [...filtered].sort((a, b) => {
      const av = column.value(a);
      const bv = column.value(b);
      // Empty/null values sort last regardless of direction.
      if (av == null || av === '') return 1;
      if (bv == null || bv === '') return -1;
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortAsc ? av - bv : bv - av;
      }
      const cmp = String(av).localeCompare(String(bv), undefined, { sensitivity: 'base' });
      return sortAsc ? cmp : -cmp;
    });
    return sorted;
  }, [songs, filters, sortKey, sortAsc]);

  const visibleIds = useMemo(() => visibleSongs.map((s) => s.id), [visibleSongs]);
  const allVisibleSelected =
    visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  const toggleSort = (key: ColumnKey) => {
    if (sortKey === key) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  };

  const setFilter = (key: ColumnKey, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        visibleIds.forEach((id) => next.delete(id));
      } else {
        visibleIds.forEach((id) => next.add(id));
      }
      return next;
    });
  };

  const handleCleanSelected = async () => {
    const targets = songs.filter((s) => selectedIds.has(s.id));
    if (targets.length === 0) return;

    setCleaning(true);
    setCleanError(null);
    setCleanResults([]);
    setCleanProgress({ done: 0, total: targets.length });

    // Drive the existing per-song auto-clean endpoint one song at a time and
    // collect per-song outcomes — each success produces a new cleaned version
    // (the original is never overwritten).
    const results: CleanResultRow[] = [];
    for (let i = 0; i < targets.length; i++) {
      const song = targets[i];
      try {
        const response = await fetch('/api/produce/auto-clean', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ song_id: song.id, aggressiveness: intensity }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          results.push({
            song_id: song.id,
            title: song.title,
            outcome: 'failed',
            reason: data.error || `HTTP ${response.status}`,
          });
        } else if (data.result?.status === 'success') {
          results.push({ song_id: song.id, title: song.title, outcome: 'succeeded', reason: null });
        } else {
          results.push({
            song_id: song.id,
            title: song.title,
            outcome: 'failed',
            reason: data.result?.error || 'Clean did not complete',
          });
        }
      } catch (err: any) {
        results.push({
          song_id: song.id,
          title: song.title,
          outcome: 'failed',
          reason: err.message || 'Request failed',
        });
      }
      setCleanResults([...results]);
      setCleanProgress({ done: i + 1, total: targets.length });
    }

    setCleaning(false);
    // Refresh the catalog so newly-cleaned songs show their indicator.
    loadSongs();
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

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header title="Produce" subtitle="Analyze and auto-clean catalog audio" />

      <main className="container mx-auto px-4 py-8">
        {/* Selection toolbar */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-4 mb-4 flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Intensity
            </label>
            <select
              value={intensity}
              onChange={(e) => setIntensity(e.target.value as Intensity)}
              disabled={cleaning}
              className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500 disabled:opacity-50"
            >
              <option value="gentle">Gentle</option>
              <option value="moderate">Moderate</option>
              <option value="aggressive">Aggressive</option>
            </select>
          </div>

          <button
            onClick={handleCleanSelected}
            disabled={cleaning || selectedIds.size === 0}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {cleaning ? 'Cleaning...' : `Clean selected (${selectedIds.size})`}
          </button>

          <span className="text-sm text-gray-600 dark:text-gray-400">
            {selectedIds.size} selected · {visibleSongs.length} of {songs.length} shown
          </span>
        </div>

        {cleanError && (
          <div className="p-3 mb-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
            {cleanError}
          </div>
        )}

        {cleanProgress && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-4 mb-4">
            <div className="flex items-center justify-between text-sm text-gray-700 dark:text-gray-300 mb-2">
              <span className="font-medium">
                {cleaning ? 'Cleaning selected songs...' : 'Clean complete'}
              </span>
              <span>
                {cleanProgress.done} / {cleanProgress.total} processed
              </span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-3">
              <div
                className="bg-green-600 h-2 rounded-full transition-all"
                style={{
                  width: `${
                    cleanProgress.total
                      ? Math.round((cleanProgress.done / cleanProgress.total) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
            {cleanResults.length > 0 && (
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
                    {cleanResults.map((r) => (
                      <tr key={r.song_id} className="border-t border-gray-200 dark:border-gray-700">
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

        {/* Catalog table */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden">
          <div className="overflow-auto max-h-[70vh]">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-900 text-left text-gray-600 dark:text-gray-300 sticky top-0 z-10">
                <tr>
                  <th className="py-2 px-3 w-10">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={toggleSelectAllVisible}
                      aria-label="Select all shown songs"
                      className="h-4 w-4"
                    />
                  </th>
                  {COLUMNS.map((col) => (
                    <th key={col.key} className="py-2 px-3">
                      <button
                        onClick={() => toggleSort(col.key)}
                        className="flex items-center gap-1 font-semibold hover:text-blue-600 dark:hover:text-blue-400"
                      >
                        {col.label}
                        {sortKey === col.key && <span>{sortAsc ? '▲' : '▼'}</span>}
                      </button>
                    </th>
                  ))}
                </tr>
                <tr>
                  <th className="px-3 pb-2"></th>
                  {COLUMNS.map((col) => (
                    <th key={col.key} className="px-3 pb-2">
                      <input
                        type="text"
                        value={filters[col.key]}
                        onChange={(e) => setFilter(col.key, e.target.value)}
                        placeholder={`Filter ${col.label.toLowerCase()}`}
                        className="w-full px-2 py-1 text-xs font-normal border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="text-gray-900 dark:text-white">
                {visibleSongs.map((song) => (
                  <tr
                    key={song.id}
                    className="border-t border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50"
                  >
                    <td className="py-2 px-3">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(song.id)}
                        onChange={() => toggleSelect(song.id)}
                        aria-label={`Select ${song.title}`}
                        className="h-4 w-4"
                      />
                    </td>
                    <td className="py-2 px-3">
                      <Link
                        href={`/produce/${song.id}`}
                        className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                      >
                        {song.title}
                      </Link>
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                      {song.genre ?? '—'}
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                      {song.tempo_bpm == null ? '—' : Math.round(song.tempo_bpm)}
                    </td>
                    <td className="py-2 px-3 text-gray-600 dark:text-gray-400">
                      {formatDuration(song.duration_seconds) || '—'}
                    </td>
                    <td className="py-2 px-3">
                      {song.cleaned ? (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200">
                          Cleaned
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400 dark:text-gray-500">—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {visibleSongs.length === 0 && (
                  <tr>
                    <td
                      colSpan={COLUMNS.length + 1}
                      className="py-6 px-3 text-center text-gray-500 dark:text-gray-400"
                    >
                      No songs match the current filters.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
}
