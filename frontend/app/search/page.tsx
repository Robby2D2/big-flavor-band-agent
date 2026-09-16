'use client';

import { useState } from 'react';
import Header from '@/components/Header';
import SearchBar, { SearchParams } from '@/components/SearchBar';
import SongList from '@/components/SongList';
import DeepSearchProgress, { DeepSearchJob } from '@/components/DeepSearchProgress';
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
  const [similarTo, setSimilarTo] = useState<string | null>(null);
  // Kept so a result can be explained on demand, after the search has returned.
  const [lastQuery, setLastQuery] = useState<string>('');
  // The in-depth run, polled while it works so its steps stay on screen.
  const [deepJob, setDeepJob] = useState<DeepSearchJob | null>(null);

  const postJson = async (url: string, body: unknown) => {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || 'Search failed');
    }
    return data;
  };

  const handleSearch = async (params: SearchParams) => {
    setLoading(true);
    setError(null);
    setSimilarTo(null);
    setResults([]);
    setDeepJob(null);
    setLastQuery(params.query);

    if (params.deep) {
      await runDeepSearch(params.query);
      return;
    }

    try {
      const data = await postJson('/api/search', { query: params.query, limit: 20 });
      setResults(data.songs || data.results || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  /**
   * In-depth search: start the background run, then follow its steps.
   *
   * Polling rather than waiting on one request — the loop makes several model
   * calls, and showing what it is doing is most of the value of asking for it.
   */
  const runDeepSearch = async (query: string) => {
    try {
      const started = await postJson('/api/search/deep/start', { query });
      const jobId = started.job_id as string;
      setDeepJob(started);

      for (;;) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const response = await fetch(`/api/search/deep/${jobId}`);
        const job = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(job.error || 'Lost track of the search');
        }
        setDeepJob(job);
        if (job.status !== 'running') {
          setResults(job.songs || []);
          if (job.status === 'failed') {
            setError(job.error || 'The search could not be completed.');
          }
          break;
        }
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handlePlaySong = (song: any) => {
    setCurrentSong(song);
  };

  const handleFindSimilar = async (song: any) => {
    setLoading(true);
    setError(null);
    setSearchSummary(null);
    setSimilarTo(song.title);

    try {
      const response = await fetch(`/api/songs/${song.id}/related?limit=20`);
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(data.error || 'Failed to find similar songs');
      }
      setResults(data.results || []);
    } catch (err: any) {
      setError(err.message || 'An error occurred');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas">
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

          {deepJob && (
            <div className="mt-6">
              <DeepSearchProgress job={deepJob} />
            </div>
          )}

          {loading && !deepJob && (
            <div className="mt-8 text-center">
              <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-text/55">
                Searching...
              </p>
            </div>
          )}

          {!loading && (results.length > 0 || searchSummary || similarTo) && (
            <div className="mt-6">
              {/* Similar-to banner */}
              {similarTo && (
                <div className="mb-4 text-sm text-text/55">
                  Songs that sound like{' '}
                  <span className="font-semibold">{similarTo}</span>
                </div>
              )}

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
                <div className="mb-4 text-sm text-text/45">
                  Found {results.length} matching {results.length === 1 ? 'song' : 'songs'}
                </div>
              )}

              {results.length > 0 && (
                <SongList
                  songs={results}
                  onPlay={handlePlaySong}
                  onFindSimilar={handleFindSimilar}
                  query={lastQuery}
                />
              )}
              {results.length === 0 && (
                <div className="text-center text-text/55">
                  {similarTo
                    ? 'No related songs available for this song.'
                    : 'No songs found. Try a different search.'}
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
