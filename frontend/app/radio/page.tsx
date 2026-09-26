'use client';

import { useCallback, useState, useEffect, useRef } from 'react';
import Header from '@/components/Header';
import { describeNowPlaying } from '@/lib/nowPlaying';
import { canRemoveQueueEntry, isEditorRole, queueActionError } from '@/lib/radioControls';
import { useAuth } from '@/lib/useAuth';

interface Song {
  id: number;
  title: string;
  duration?: number;
  /** Per-reader: whether the signed-in user is the one who queued this song (RAD-13). */
  added_by_me?: boolean;
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
  // Reported by the backend's reconciliation against the live stream (issue #101).
  stream_known?: boolean;
  current_song_source?: string | null;
  stream_duration?: number | null;
}

/** An in-page result for a queue action — RAD-09 needs failures visible, not alerted. */
interface Notice {
  kind: 'error' | 'ok';
  text: string;
}

export default function RadioPage() {
  const [radioState, setRadioState] = useState<RadioState | null>(null);
  const [loading, setLoading] = useState(true);
  const [listenerId, setListenerId] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [request, setRequest] = useState('');
  const [adding, setAdding] = useState(false);
  const audioRef = useRef<HTMLAudioElement>(null);
  const lastSongIdRef = useRef<number | null>(null);

  // The session's real role, read for display only: it decides which controls are
  // offered, never whether an action is allowed (ACCT-03, ACCT-04). This page used to
  // hardcode 'listener', which left every editor control unreachable (issue #102).
  const { user, isLoading: authLoading } = useAuth();
  const userRole = user?.role ?? 'listener';

  const fetchRadioState = useCallback(async () => {
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
  }, [listenerId]);

  // Poll radio state
  useEffect(() => {
    fetchRadioState();
    const interval = setInterval(fetchRadioState, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [fetchRadioState]);

  const handleSkip = async () => {
    setNotice(null);
    try {
      const response = await fetch('/api/radio/skip', {
        method: 'POST',
      });

      // A skip now moves the audio on the stream, so it can genuinely fail — and a
      // failed queue action has to say so rather than look like it worked (RAD-09).
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setNotice({
          kind: 'error',
          text: queueActionError(
            response.status,
            body,
            'Could not skip the song — the stream did not respond.'
          ),
        });
        return;
      }

      await fetchRadioState();
    } catch (error) {
      console.error('Error skipping song:', error);
      setNotice({
        kind: 'error',
        text: 'Could not skip the song — the stream did not respond.',
      });
    }
  };

  const handleRemove = async (songId: number) => {
    setNotice(null);
    try {
      const response = await fetch('/api/radio/remove', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ song_id: songId }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setNotice({
          kind: 'error',
          text: queueActionError(
            response.status,
            body,
            'Could not remove that song from the queue.'
          ),
        });
        return;
      }

      // Drop it on screen at once (RAD-08), then refetch so the server's queue — not
      // this guess — is what the page settles on.
      setRadioState((previous) =>
        previous
          ? {
              ...previous,
              queue: previous.queue.filter((song) => song.id !== songId),
              queue_length: Math.max(0, previous.queue_length - 1),
            }
          : previous
      );
      await fetchRadioState();
    } catch (error) {
      console.error('Error removing song:', error);
      setNotice({
        kind: 'error',
        text: 'Could not remove that song from the queue.',
      });
    }
  };

  const handleTogglePlayback = async () => {
    setNotice(null);
    const pausing = Boolean(radioState?.is_playing);
    try {
      const response = await fetch(pausing ? '/api/radio/pause' : '/api/radio/play', {
        method: 'POST',
      });

      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setNotice({
          kind: 'error',
          text: queueActionError(
            response.status,
            body,
            pausing ? 'Could not pause the radio.' : 'Could not resume the radio.'
          ),
        });
        return;
      }

      await fetchRadioState();
    } catch (error) {
      console.error('Error changing radio playback:', error);
      setNotice({
        kind: 'error',
        text: pausing ? 'Could not pause the radio.' : 'Could not resume the radio.',
      });
    }
  };

  const handleAddToQueue = async (event: React.FormEvent) => {
    event.preventDefault();
    const message = request.trim();
    if (!message || adding) return;

    setNotice(null);
    setAdding(true);
    try {
      const response = await fetch('/api/radio', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message }),
      });

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        setNotice({
          kind: 'error',
          text: queueActionError(response.status, body, 'Could not add anything to the queue.'),
        });
        return;
      }

      // Nothing added is a failed request as far as the user is concerned, so it says
      // so rather than clearing the box and looking like it worked (RAD-09).
      if (!body?.added_count) {
        setNotice({
          kind: 'error',
          text: 'Nothing matched that, so nothing was added to the queue.',
        });
        return;
      }

      setRequest('');
      setNotice({
        kind: 'ok',
        text: `Added ${body.added_count} song${body.added_count === 1 ? '' : 's'} to the queue.`,
      });
      await fetchRadioState();
    } catch (error) {
      console.error('Error adding to the queue:', error);
      setNotice({ kind: 'error', text: 'Could not add anything to the queue.' });
    } finally {
      setAdding(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const isEditor = isEditorRole(userRole);

  // The radio is an always-on broadcast: treat it as LIVE whenever the backend
  // reports playback OR the listener is actively tuned in (hearing audio). This
  // prevents the status pill from reading PAUSED while a stream is audibly
  // playing (issue #79).
  const isLive = Boolean(radioState?.is_playing) || isListening;

  // What is on the air, as the stream itself reported it (issue #101).
  const nowPlaying = describeNowPlaying(radioState);

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

  if (loading || authLoading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-text/55">Tuning in...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
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

        {/* What just happened to the queue, said on the page rather than in a browser
            alert that leaves nothing behind to read (RAD-09, PLAT-07). */}
        {notice && (
          <div
            role="status"
            className={`mb-6 flex items-start justify-between gap-3 rounded-lg border p-4 text-sm ${
              notice.kind === 'error'
                ? 'border-red-500/40 bg-red-500/10 text-red-200'
                : 'border-green-500/40 bg-green-500/10 text-green-200'
            }`}
          >
            <span>{notice.text}</span>
            <button
              onClick={() => setNotice(null)}
              className="shrink-0 text-text/55 hover:text-text"
              aria-label="Dismiss message"
            >
              ✕
            </button>
          </div>
        )}

        {/* Now Playing */}
        <div className="bg-panel rounded-lg shadow-lg p-8 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-2xl font-bold text-text">
              Now Playing
            </h2>
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${isLive ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
              <span className="text-sm text-text/55">
                {isLive ? 'LIVE' : 'PAUSED'}
              </span>
            </div>
          </div>

          {nowPlaying.kind === 'unknown' ? (
            <p className="text-text/55 mb-4">
              Can&apos;t reach the stream right now, so we don&apos;t know what&apos;s on the air.
              Retrying every few seconds.
            </p>
          ) : nowPlaying.song ? (
            <div>
              <h3 className="text-xl font-semibold text-text mb-2">
                {nowPlaying.song.title}
              </h3>
              {nowPlaying.kind === 'fallback' && (
                <p className="text-text/55 mb-2 text-sm">
                  Catalog music the stream picked — nothing is queued right now. Add some songs
                  to take over the airwaves!
                </p>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-text/55">
                  {formatTime(nowPlaying.position)}
                  {nowPlaying.duration !== null && ` / ${formatTime(nowPlaying.duration)}`}
                </span>
                {/* Changing what everyone hears is editor+ (ACCT-15); a listener is not
                    shown a control that would only be refused (ACCT-08). */}
                {isEditor && (
                  <>
                    <button
                      onClick={handleSkip}
                      className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
                    >
                      Skip →
                    </button>
                    <button
                      onClick={handleTogglePlayback}
                      className="px-4 py-2 bg-raised text-text rounded-lg hover:bg-well text-sm"
                    >
                      {radioState?.is_playing ? 'Pause' : 'Resume'}
                    </button>
                  </>
                )}
              </div>
              {/* Progress bar — only when something knows how long the track is (CAT-02) */}
              {nowPlaying.progress !== null && (
                <div className="w-full bg-white/10 rounded-full h-2 mt-4">
                  <div
                    className="bg-blue-600 h-2 rounded-full transition-all"
                    style={{ width: `${nowPlaying.progress * 100}%` }}
                  />
                </div>
              )}
            </div>
          ) : (
            <p className="text-text/55 mb-4">
              Nothing recognisable on the air. Add some songs to get started!
            </p>
          )}

          {/* Audio Player Controls - Always visible */}
          <div className="mt-6 pt-6 border-t border-white/8">
            <div className="flex flex-wrap items-center gap-4">
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

              <div className="flex-1 min-w-[8rem]">
                <span className="text-sm font-medium text-text/70">
                  {isListening ? 'Listening...' : 'Click to tune in'}
                </span>
              </div>

              {/* Volume Control */}
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-text/45" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.707.707L4.586 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.586l3.707-3.707a1 1 0 011.09-.217zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clipRule="evenodd" />
                </svg>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.1"
                  value={volume}
                  onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                  className="w-24 h-2 bg-white/10 rounded-lg appearance-none cursor-pointer"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Queue */}
        <div className="bg-panel rounded-lg shadow-lg p-6">
          <h2 className="text-xl font-semibold text-text mb-4">
            Up Next ({radioState?.queue_length || 0} songs)
          </h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {radioState?.queue && radioState.queue.length > 0 ? (
              radioState.queue.map((song, index) => (
                <div
                  key={song.id}
                  className="flex items-center justify-between gap-2 p-3 bg-well rounded-lg"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text/45">
                        {index + 1}.
                      </span>
                      <span className="text-sm font-medium text-text truncate">
                        {song.title}
                      </span>
                    </div>
                  </div>
                  {/* An editor may remove any song; anyone else only their own additions
                      (ACCT-05, ACCT-15). Hiding it is the courtesy; the backend decides. */}
                  {canRemoveQueueEntry(song, userRole) && (
                    <button
                      onClick={() => handleRemove(song.id)}
                      className="shrink-0 text-red-600 hover:text-red-700 text-sm px-2 py-1"
                    >
                      Remove
                    </button>
                  )}
                </div>
              ))
            ) : (
              <p className="text-text/45 text-sm">
                Queue is empty
              </p>
            )}
          </div>

          {/* Adding to the queue is open to every signed-in user (RAD-06) — the radio
              page used to only point at the Search page for it. */}
          <form onSubmit={handleAddToQueue} className="mt-6 flex flex-wrap gap-2">
            <label htmlFor="radio-request" className="sr-only">
              Ask for songs to add to the queue
            </label>
            <input
              id="radio-request"
              type="text"
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder="Add songs — a title, or something like &quot;play something mellow&quot;"
              className="flex-1 min-w-[12rem] rounded-lg bg-well px-4 py-2 text-sm text-text placeholder:text-text/40 border border-white/10 focus:outline-none focus:border-blue-500"
            />
            <button
              type="submit"
              disabled={adding || request.trim() === ''}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {adding ? 'Adding...' : 'Add to queue'}
            </button>
          </form>

          <div className="mt-4 p-4 bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg">
            <p className="text-sm text-blue-800 dark:text-blue-200">
              <strong>Tip:</strong> You can also add songs from the Search page using the kebab
              menu. Songs you add are yours to remove again.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
