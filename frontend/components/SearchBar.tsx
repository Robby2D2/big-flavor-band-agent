'use client';

import { useState, FormEvent } from 'react';

export type SearchMode = 'natural' | 'text' | 'lyrics' | 'tempo' | 'audio' | 'hybrid';

export interface SearchParams {
  mode: SearchMode;
  query?: string;
  minBpm?: number | null;
  maxBpm?: number | null;
}

interface SearchBarProps {
  onSearch: (params: SearchParams) => void;
  loading?: boolean;
}

const MODES: { value: SearchMode; label: string }[] = [
  { value: 'natural', label: 'Natural language' },
  { value: 'text', label: 'Text / mood' },
  { value: 'lyrics', label: 'Lyrics' },
  { value: 'tempo', label: 'Tempo (BPM)' },
  { value: 'audio', label: 'Sounds like…' },
  { value: 'hybrid', label: 'Text + tempo' },
];

export default function SearchBar({ onSearch, loading = false }: SearchBarProps) {
  const [mode, setMode] = useState<SearchMode>('natural');
  const [query, setQuery] = useState('');
  const [minBpm, setMinBpm] = useState('');
  const [maxBpm, setMaxBpm] = useState('');

  const parseBpm = (value: string): number | null => {
    const n = parseFloat(value);
    return Number.isFinite(n) ? n : null;
  };

  const canSubmit = (): boolean => {
    if (loading) return false;
    if (mode === 'tempo') {
      return minBpm.trim() !== '' || maxBpm.trim() !== '';
    }
    return query.trim() !== '';
  };

  const submit = () => {
    if (!canSubmit()) return;

    if (mode === 'tempo') {
      onSearch({
        mode,
        minBpm: parseBpm(minBpm),
        maxBpm: parseBpm(maxBpm),
      });
      return;
    }

    if (mode === 'hybrid') {
      onSearch({
        mode,
        query: query.trim(),
        minBpm: parseBpm(minBpm),
        maxBpm: parseBpm(maxBpm),
      });
      return;
    }

    onSearch({ mode, query: query.trim() });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const queryPlaceholder = (): string => {
    switch (mode) {
      case 'lyrics':
        return "Lyrics keyword (e.g. 'sunshine')";
      case 'audio':
        return 'Title of a song to sound like…';
      case 'hybrid':
        return "Text / mood (e.g. 'calm acoustic')";
      case 'text':
        return "Text / mood (e.g. 'upbeat love songs')";
      default:
        return "Search for songs... (e.g., 'upbeat songs about love')";
    }
  };

  const showQuery = mode !== 'tempo';
  const showTempo = mode === 'tempo' || mode === 'hybrid';

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setMode(m.value)}
            disabled={loading}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
              mode === m.value
                ? 'bg-blue-600 text-white'
                : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        {showQuery && (
          <div className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={queryPlaceholder()}
              className="w-full px-6 py-4 text-lg border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-800 dark:text-white"
              disabled={loading}
            />
          </div>
        )}

        {showTempo && (
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={minBpm}
              onChange={(e) => setMinBpm(e.target.value)}
              placeholder="Min BPM"
              min={0}
              className="w-32 px-4 py-2 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-800 dark:text-white"
              disabled={loading}
            />
            <span className="text-gray-500 dark:text-gray-400">to</span>
            <input
              type="number"
              value={maxBpm}
              onChange={(e) => setMaxBpm(e.target.value)}
              placeholder="Max BPM"
              min={0}
              className="w-32 px-4 py-2 border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-800 dark:text-white"
              disabled={loading}
            />
          </div>
        )}

        <button
          type="submit"
          disabled={!canSubmit()}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {loading ? 'Searching...' : 'Search'}
        </button>
      </form>
    </div>
  );
}
