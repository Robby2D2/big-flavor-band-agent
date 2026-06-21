'use client';

import { useState, useEffect, useRef } from 'react';
import Header from '@/components/Header';

interface Song {
  id: number;
  title: string;
  duration?: number;
  [key: string]: any;
}

interface RadioState {
  current_song: Song | null;
  queue: Song[];
  is_playing: boolean;
  position: number;
  queue_length: number;
  listener_id?: string;
  active_listeners?: number;
}

export default function RadioPage() {
  const [radioState, setRadioState] = useState<RadioState | null>(null);
  const [loading, setLoading] = useState(true);
  const [userRole, setUserRole] = useState<string>('listener');
  const [listenerId, setListenerId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const streamLoadedRef = useRef(false);

  // Check user role
  useEffect(() => {
    const checkRole = async () => {
      try {
        const response = await fetch('/api/auth/me');
        if (response.ok) {
          const user = await response.json();
          // For now, assume listener - in production, fetch from backend
          // This is a simplified version - you'd need to add role to the user object
          setUserRole('listener');
        }
      } catch (error) {
        console.error('Error checking user role:', error);
      }
    };
    checkRole();
  }, []);

  // Load stream and poll radio state
  useEffect(() => {
    const fetchRadioState = async () => {
      try {
        // Include listener_id in request if we have one
        const url = listenerId ? `/api/radio?listener_id=${listenerId}` : '/api/radio';
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          setRadioState(data);

          // Store listener_id if returned and we don't have one yet
          if (data.listener_id && !listenerId) {
            setListenerId(data.listener_id);
          }

          // Auto-load stream on first load
          if (!streamLoadedRef.current && audioRef.current) {
            audioRef.current.src = '/stream';
            audioRef.current.volume = 0.8;
            streamLoadedRef.current = true;
          }
        }
      } catch (error) {
        console.error('Error fetching radio state:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchRadioState();
    const interval = setInterval(fetchRadioState, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [listenerId]);

  const handleSkip = async () => {
    try {
      const response = await fetch('/api/radio/skip', {
        method: 'POST',
      });

      if (response.status === 403) {
        alert('Access denied. Editor role required.');
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to skip song');
      }
    } catch (error) {
      console.error('Error skipping song:', error);
    }
  };

  const handleRemove = async (songId: number) => {
    try {
      const response = await fetch('/api/radio/remove', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ song_id: songId }),
      });

      if (response.status === 403) {
        alert('Access denied. Editor role required.');
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to remove song');
      }
    } catch (error) {
      console.error('Error removing song:', error);
    }
  };

  const isEditor = userRole === 'editor' || userRole === 'admin';

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Tuning in...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header
        title="BigFlavor Radio"
        subtitle="Live radio - everyone hears the same thing!"
      />

      <main className="container mx-auto px-4 py-8">
        {/* Live Radio Player */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              Live Radio Stream
            </h2>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-red-600 animate-pulse" />
              <span className="text-sm text-red-600 font-semibold">
                LIVE
              </span>
            </div>
          </div>

          {/* Audio Player */}
          <audio
            ref={audioRef}
            preload="none"
            controls
            className="w-full"
            style={{ maxWidth: '100%' }}
          />

          {isEditor && radioState?.current_song && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400">Editor Controls</p>
                  <p className="text-xs text-gray-500 dark:text-gray-500">Currently queued: {radioState.current_song.title}</p>
                </div>
                <button
                  onClick={handleSkip}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm flex items-center gap-2"
                >
                  Skip to Next
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M4.555 5.168A1 1 0 003 6v8a1 1 0 001.555.832L10 11.202V14a1 1 0 001.555.832l6-4a1 1 0 000-1.664l-6-4A1 1 0 0010 6v2.798l-5.445-3.63z" />
                  </svg>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Queue */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
            Up Next ({radioState?.queue_length || 0} songs)
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {radioState?.queue && radioState.queue.length > 0 ? (
              radioState.queue.map((song, index) => (
                <div
                  key={song.id}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700 rounded-lg"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        {index + 1}.
                      </span>
                      <span className="text-sm font-medium text-gray-900 dark:text-white">
                        {song.title}
                      </span>
                    </div>
                  </div>
                  {isEditor && (
                    <button
                      onClick={() => handleRemove(song.id)}
                      className="text-red-600 hover:text-red-700 text-sm px-2"
                    >
                      Remove
                    </button>
                  )}
                </div>
              ))
            ) : (
              <p className="text-gray-500 dark:text-gray-400 text-sm">
                Queue is empty
              </p>
            )}
          </div>

          <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              <strong>Tip:</strong> You can request songs by adding them to the radio queue from the Search page using the kebab menu.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
