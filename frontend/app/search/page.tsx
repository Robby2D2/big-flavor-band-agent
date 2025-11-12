'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import SearchBar from '@/components/SearchBar';
import SongList from '@/components/SongList';
import AudioPlayer from '@/components/AudioPlayer';

export default function SearchPage() {
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentSong, setCurrentSong] = useState<any>(null);
  const [agentResponse, setAgentResponse] = useState<string>('');

  const handleSearch = async (query: string) => {
    setLoading(true);
    setError(null);
    setAgentResponse('');

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
      setAgentResponse(data.response || '');
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

          {agentResponse && (
            <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
              <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">
                Agent Response:
              </h3>
              <p className="text-blue-800 dark:text-blue-200 whitespace-pre-wrap">
                {agentResponse}
              </p>
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

          {!loading && results.length > 0 && (
            <div className="mt-8">
              <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-4">
                Results ({results.length})
              </h2>
              <SongList songs={results} onPlay={handlePlaySong} />
            </div>
          )}

          {!loading && results.length === 0 && !error && agentResponse && (
            <div className="mt-8 text-center text-gray-600 dark:text-gray-400">
              No songs found. Try a different search.
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
