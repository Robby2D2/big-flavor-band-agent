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
  const [djMessage, setDjMessage] = useState('');
  const [djResponse, setDjResponse] = useState('');
  const [requesting, setRequesting] = useState(false);
  const [userRole, setUserRole] = useState<string>('listener');
  const [listenerId, setListenerId] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);
  const lastSongIdRef = useRef<number | null>(null);

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

  // Poll radio state
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

          // Sync audio player with server state
          if (audioRef.current && data.current_song) {
            // If song changed, load new song
            if (data.current_song.id !== lastSongIdRef.current) {
              audioRef.current.src = `/api/audio/${data.current_song.id}`;
              audioRef.current.currentTime = data.position;
              lastSongIdRef.current = data.current_song.id;

              if (data.is_playing) {
                audioRef.current.play().catch(console.error);
              }
            } else {
              // Sync position if drift is more than 2 seconds
              const drift = Math.abs(audioRef.current.currentTime - data.position);
              if (drift > 2) {
                audioRef.current.currentTime = data.position;
              }

              // Sync play/pause state
              if (data.is_playing && audioRef.current.paused) {
                audioRef.current.play().catch(console.error);
              } else if (!data.is_playing && !audioRef.current.paused) {
                audioRef.current.pause();
              }
            }
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

  const handleDJRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!djMessage.trim()) return;

    setRequesting(true);
    setDjResponse('');

    try {
      const response = await fetch('/api/radio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: djMessage,
        }),
      });

      if (response.status === 403) {
        setDjResponse('Access denied. You must be logged in to request songs.');
        setRequesting(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to add songs to queue');
      }

      const data = await response.json();
      setDjResponse(data.response || `Added ${data.added_count} songs to queue`);
      setDjMessage('');
    } catch (error: any) {
      setDjResponse(`Error: ${error.message}`);
    } finally {
      setRequesting(false);
    }
  };

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

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
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
        {/* Hidden audio player */}
        <audio ref={audioRef} />

        {/* Now Playing */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-gray-900 dark:text-white">
              Now Playing
            </h2>
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${radioState?.is_playing ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
              <span className="text-sm text-gray-600 dark:text-gray-400">
                {radioState?.is_playing ? 'LIVE' : 'PAUSED'}
              </span>
            </div>
          </div>

          {radioState?.current_song ? (
            <div>
              <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                {radioState.current_song.title}
              </h3>
              <div className="flex items-center gap-4">
                <span className="text-gray-600 dark:text-gray-400">
                  {formatTime(radioState.position)} / {formatTime(radioState.current_song.duration || 0)}
                </span>
                {isEditor && (
                  <button
                    onClick={handleSkip}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
                  >
                    Skip →
                  </button>
                )}
              </div>
              {/* Progress bar */}
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mt-4">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all"
                  style={{
                    width: `${(radioState.position / (radioState.current_song.duration || 1)) * 100}%`
                  }}
                />
              </div>
            </div>
          ) : (
            <p className="text-gray-600 dark:text-gray-400">
              No song currently playing. {isEditor && 'Add some songs to get started!'}
            </p>
          )}
        </div>

        <div className="grid md:grid-cols-2 gap-6">
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
          </div>

          {/* DJ Request */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Request Songs
            </h2>
            <form onSubmit={handleDJRequest} className="space-y-4">
              <textarea
                value={djMessage}
                onChange={(e) => setDjMessage(e.target.value)}
                placeholder="Ask the DJ for songs... (e.g., 'Play some upbeat rock songs' or 'Add slow acoustic ballads')"
                disabled={requesting}
                className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-700 dark:text-white resize-none disabled:opacity-50"
                rows={4}
              />
              <button
                type="submit"
                disabled={requesting || !djMessage.trim()}
                className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed font-medium"
              >
                {requesting ? 'Requesting...' : 'Add to Queue'}
              </button>
            </form>

            {djResponse && (
              <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900 rounded-lg">
                <p className="text-sm text-blue-900 dark:text-blue-100 whitespace-pre-wrap">
                  {djResponse}
                </p>
              </div>
            )}

            {!isEditor && (
              <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg">
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  <strong>Tip:</strong> You can request songs! Only editors and admins can skip songs or remove them from the queue.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
