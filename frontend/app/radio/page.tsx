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
  const [isListening, setIsListening] = useState(false);
  const [volume, setVolume] = useState(0.8);
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

          // Track current song for display (stream is continuous)
          if (data.current_song) {
            lastSongIdRef.current = data.current_song.id;
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
  }, [listenerId, isListening]);

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

  const toggleListening = () => {
    if (!audioRef.current) return;

    if (isListening) {
      audioRef.current.pause();
      audioRef.current.src = '';
      setIsListening(false);
    } else {
      // Use the Icecast stream URL
      const audio = audioRef.current;
      audio.src = '/stream';
      audio.volume = volume;
      audio.play();
      setIsListening(true);
    }
  };

  const handleVolumeChange = (newVolume: number) => {
    setVolume(newVolume);
    if (audioRef.current) {
      audioRef.current.volume = newVolume;
    }
  };

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
        {/* Audio element */}
        <audio
          ref={audioRef}
          preload="none"
          controls
          style={{ display: 'block', margin: '20px auto', width: '100%', maxWidth: '600px' }}
        />

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
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              No song currently playing. {isEditor && 'Add some songs to get started!'}
            </p>
          )}

          {/* Audio Player Controls - Always visible */}
          <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
            <div className="flex items-center gap-4">
              {/* Play/Stop Button */}
              <button
                onClick={toggleListening}
                className={`flex items-center justify-center w-14 h-14 rounded-full transition-colors ${
                  isListening
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-green-600 hover:bg-green-700 text-white'
                }`}
              >
                {isListening ? (
                  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8 7a1 1 0 00-1 1v4a1 1 0 001 1h4a1 1 0 001-1V8a1 1 0 00-1-1H8z" clipRule="evenodd" />
                  </svg>
                ) : (
                  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                  </svg>
                )}
              </button>

              <div className="flex-1">
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {isListening ? 'Listening...' : 'Click to tune in'}
                </span>
              </div>

              {/* Volume Control */}
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-gray-500" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clipRule="evenodd" />
                </svg>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={volume}
                  onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                  className="w-24 h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
                />
              </div>
            </div>
          </div>
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
