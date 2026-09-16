'use client';

import { useState, FormEvent } from 'react';

export interface SearchParams {
  query: string;
  /** Run the agentic loop instead of a single semantic pass. */
  deep: boolean;
}

interface SearchBarProps {
  onSearch: (params: SearchParams) => void;
  loading?: boolean;
}

/**
 * One box, one question.
 *
 * This used to carry six mode buttons — natural language, text/mood, lyrics,
 * tempo, sounds-like, text+tempo — which asked the listener to know which
 * retrieval strategy their question needed before they had asked it. Semantic
 * search answers nearly all of them, and "In depth" hands the rest to a model
 * that picks the tools itself.
 */
export default function SearchBar({ onSearch, loading = false }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const [deep, setDeep] = useState(false);

  const canSubmit = !loading && query.trim().length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    onSearch({ query: query.trim(), deep });
  };

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="space-y-3">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            deep
              ? 'Ask a question — “which songs are about leaving home, and do any sound hopeful?”'
              : 'Describe what you want to hear — “upbeat country about home”'
          }
          aria-label="Search the catalogue"
          className="w-full px-6 py-4 text-lg border-2 border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-800 dark:text-white"
          disabled={loading}
        />

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={!canSubmit}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {loading ? (deep ? 'Working…' : 'Searching…') : 'Search'}
          </button>

          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={deep}
              onChange={(e) => setDeep(e.target.checked)}
              disabled={loading}
              className="w-4 h-4 accent-blue-600"
            />
            <span className="text-sm font-medium text-text">In depth</span>
          </label>

          <span className="text-sm text-text/45">
            {deep
              ? 'searches, reads what it finds, searches again, then answers with citations · takes a minute'
              : 'one fast pass over the catalogue'}
          </span>
        </div>
      </form>
    </div>
  );
}
