'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import SearchBar from '@/components/SearchBar';
import SongList from '@/components/SongList';
import AudioPlayer from '@/components/AudioPlayer';

interface SearchSummary {
  technique: string;
  accuracy: string;
  description: string;
}

export default function SearchPage() {
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSong, setCurrentSong] = useState<any>(null);
  const [searchSummary, setSearchSummary] = useState<SearchSummary | null>(null);

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setSearchSummary(null);

    try {
      const response = await fetch('/api/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, limit: 20 }),
      });

      if (!response.ok) {
        throw new Error('Search failed');
      }

      const data = await response.json();
      setSearchSummary(data.search_summary || null);
      setResults(data.songs || data.results || []);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
    } finally {
      setLoading(false);
    }
  };

  const handlePlaySong = (song: any) => {
    setCurrentSong(song);
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header
        title="Search BigFlavor Songs"
        subtitle="Use natural language to find the perfect song"
      />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto">
          <SearchBar onSearch={handleSearch} loading={loading} />

          {error && (
            <div className="mt-4 p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded">
              {error}
            </div>
          )}

          {loading && (
            <div className="mt-8 text-center">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-gray-600 dark:text-gray-400">
                Searching...
              </p>
            </div>
          )}

          {!loading && (results.length > 0 || searchSummary) && (
            <div className="mt-6">
              {/* Search Summary Card */}
              {searchSummary && (
                <div className="mb-6 bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/40 dark:to-purple-900/40 rounded-xl p-6 border border-indigo-100 dark:border-indigo-800 shadow-sm">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0">
                      <div className="w-10 h-10 bg-indigo-100 dark:bg-indigo-800 rounded-lg flex items-center justify-center">
                        <svg className="w-6 h-6 text-indigo-600 dark:text-indigo-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                        </svg>
                      </div>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-semibold text-indigo-900 dark:text-indigo-100 mb-2">
                        Search Analysis
                      </h3>

                      {/* Technique and Accuracy badges */}
                      <div className="flex flex-wrap gap-2 mb-3">
                        {searchSummary.technique && (
                          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-800 text-indigo-700 dark:text-indigo-200">
                            <svg className="w-3.5 h-3.5 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                            {searchSummary.technique}
                          </span>
                        )}
                        {searchSummary.accuracy && (
                          <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-green-100 dark:bg-green-800 text-green-700 dark:text-green-200">
                            <svg className="w-3.5 h-3.5 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {searchSummary.accuracy}
                          </span>
                        )}
                      </div>

                      {/* Description */}
                      {searchSummary.description && (
                        <p className="text-sm text-indigo-800 dark:text-indigo-200 leading-relaxed">
                          {searchSummary.description}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Results count */}
              {results.length > 0 && (
                <div className="mb-4 text-sm text-gray-500 dark:text-gray-400">
                  Found {results.length} matching {results.length === 1 ? 'song' : 'songs'}
                </div>
              )}

              {results.length > 0 && (
                <SongList songs={results} onPlay={handlePlaySong} />
              )}
              {results.length === 0 && (
                <div className="text-center text-gray-600 dark:text-gray-400">
                  No songs found. Try a different search.
                </div>
              )}
            </div>
          )}
        </div>
      </main>

      {currentSong && (
        <AudioPlayer
          song={currentSong}
          onClose={() => setCurrentSong(null)}
        />
      )}
    </div>
  );
}
