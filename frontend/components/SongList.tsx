'use client';

import { useState } from 'react';

interface Song {
  id: number;
  title: string;
  genre?: string;
  tempo_bpm?: number;
  key?: string;
  duration_seconds?: number;
  mood?: string;
  energy?: string;
  recording_date?: string;
  created_at?: string;
  updated_at?: string;
  similarity?: number;
  max_similarity?: number;
  score?: number;
  commentary?: string;
  match_reason?: string;
  audio_url?: string;
}

interface SongListProps {
  songs: Song[];
  onPlay: (song: Song) => void;
  onAddToQueue?: (song: Song) => void;
}

export default function SongList({ songs, onPlay, onAddToQueue }: SongListProps) {
  const [addingToQueue, setAddingToQueue] = useState<number | null>(null);
  const [queueMessage, setQueueMessage] = useState<{ id: number; message: string } | null>(null);
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);
  const [lyricsModal, setLyricsModal] = useState<{ song: Song; lyrics: string } | null>(null);
  const [loadingLyrics, setLoadingLyrics] = useState<number | null>(null);
  const [showInfoId, setShowInfoId] = useState<number | null>(null);

  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleAddToQueue = async (song: Song) => {
    if (onAddToQueue) {
      onAddToQueue(song);
      return;
    }

    // Default queue behavior - call radio API
    setAddingToQueue(song.id);
    try {
      const response = await fetch('/api/radio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          song_id: song.id,
        }),
      });

      if (response.ok) {
        setQueueMessage({ id: song.id, message: 'Added to radio!' });
        setTimeout(() => setQueueMessage(null), 2000);
      } else {
        const errorData = await response.json().catch(() => ({}));
        console.error('Failed to add to radio:', response.status, errorData);
        setQueueMessage({ id: song.id, message: 'Failed to add' });
        setTimeout(() => setQueueMessage(null), 2000);
      }
    } catch (error) {
      setQueueMessage({ id: song.id, message: 'Error adding to queue' });
      setTimeout(() => setQueueMessage(null), 2000);
    } finally {
      setAddingToQueue(null);
    }
  };

  const handleViewLyrics = async (song: Song) => {
    setOpenMenuId(null);
    setLoadingLyrics(song.id);
    try {
      const response = await fetch(`/api/songs/${song.id}/lyrics`);
      if (response.ok) {
        const data = await response.json();
        setLyricsModal({ song, lyrics: data.lyrics || 'No lyrics available' });
      } else {
        setLyricsModal({ song, lyrics: 'Lyrics not found' });
      }
    } catch (error) {
      setLyricsModal({ song, lyrics: 'Error loading lyrics' });
    } finally {
      setLoadingLyrics(null);
    }
  };

  return (
    <div className="space-y-4">
      {songs.map((song) => (
        <div
          key={song.id}
          className="bg-white dark:bg-gray-800 rounded-xl shadow-md hover:shadow-xl transition-all duration-200 border border-gray-100 dark:border-gray-700"
        >
          {/* Card Header */}
          <div className="p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-bold text-gray-900 dark:text-white truncate">
                    {song.title}
                  </h3>

                  {/* Info icon for match reason */}
                  {(song.match_reason || song.commentary) && (
                    <div className="relative">
                      <button
                        onClick={() => setShowInfoId(showInfoId === song.id ? null : song.id)}
                        className="p-1 text-gray-400 hover:text-blue-500 transition-colors"
                        title="Why this matched"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </button>

                      {showInfoId === song.id && (
                        <div className="absolute left-0 top-8 z-20 w-64 p-3 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700">
                          <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                            {song.match_reason || song.commentary}
                          </p>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Tags */}
                <div className="mt-3 flex flex-wrap gap-2">
                  {song.genre && (
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-purple-100 dark:bg-purple-900/50 text-purple-700 dark:text-purple-200">
                      {song.genre}
                    </span>
                  )}
                  {song.mood && (
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-200">
                      {song.mood}
                    </span>
                  )}
                  {song.energy && (
                    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 dark:bg-orange-900/50 text-orange-700 dark:text-orange-200">
                      {song.energy}
                    </span>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => onPlay(song)}
                  className="flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors shadow-sm hover:shadow"
                >
                  <svg
                    className="w-5 h-5"
                    fill="currentColor"
                    viewBox="0 0 20 20"
                  >
                    <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                  </svg>
                  Play
                </button>

                {/* Dropdown Menu */}
                <div className="relative">
                  <button
                    onClick={() => setOpenMenuId(openMenuId === song.id ? null : song.id)}
                    className="flex items-center justify-center p-2.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg transition-colors"
                  >
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                    </svg>
                  </button>

                  {openMenuId === song.id && (
                    <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-10">
                      <button
                        onClick={() => {
                          setOpenMenuId(null);
                          handleAddToQueue(song);
                        }}
                        disabled={addingToQueue === song.id}
                        className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 first:rounded-t-lg"
                      >
                        {addingToQueue === song.id ? (
                          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                          </svg>
                        )}
                        {queueMessage?.id === song.id ? queueMessage.message : 'Play on Radio'}
                      </button>
                      <button
                        onClick={() => handleViewLyrics(song)}
                        disabled={loadingLyrics === song.id}
                        className="w-full flex items-center gap-3 px-4 py-3 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 last:rounded-b-lg border-t border-gray-100 dark:border-gray-700"
                      >
                        {loadingLyrics === song.id ? (
                          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                          </svg>
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                          </svg>
                        )}
                        View Lyrics
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Metadata Row */}
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
              <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm text-gray-600 dark:text-gray-400">
                {song.tempo_bpm && (
                  <div className="flex items-center gap-1.5">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <span>{Math.round(song.tempo_bpm)} BPM</span>
                  </div>
                )}
                {song.key && (
                  <div className="flex items-center gap-1.5">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3" />
                    </svg>
                    <span>{song.key}</span>
                  </div>
                )}
                {song.duration_seconds && (
                  <div className="flex items-center gap-1.5">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>{formatDuration(song.duration_seconds)}</span>
                  </div>
                )}
                {(song.similarity || song.max_similarity || song.score) && (
                  <div className="flex items-center gap-1.5">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span className="text-green-600 dark:text-green-400 font-medium">
                      {((song.similarity || song.max_similarity || song.score || 0) * 100).toFixed(0)}% match
                    </span>
                  </div>
                )}
                {song.recording_date && (
                  <div className="flex items-center gap-1.5">
                    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    <span>Recorded: {new Date(song.recording_date).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ))}

      {/* Lyrics Modal */}
      {lyricsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                {lyricsModal.song.title}
              </h3>
              <button
                onClick={() => setLyricsModal(null)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 overflow-y-auto flex-1">
              <pre className="whitespace-pre-wrap font-sans text-gray-700 dark:text-gray-300 leading-relaxed">
                {lyricsModal.lyrics}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
