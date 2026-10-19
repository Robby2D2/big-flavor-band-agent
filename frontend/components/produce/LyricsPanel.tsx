'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { LyricTimings } from '@/lib/lyricTimings';

// ---------------------------------------------------------------------------
// Lyrics tab: view / hand-edit / re-extract a song's lyrics.
//
// Reads GET /api/produce/songs/{id}/lyrics, saves edits via PUT (which re-embeds
// so lyric search stays consistent), and can kick off a background Whisper
// re-extraction (POST .../lyrics/extract) that it polls to completion, then
// reloads the freshly transcribed text.
//
// Extraction also stores per-line timings that drive follow-along highlighting
// during playback. An edit that changes the words invalidates them, so the
// backend marks them stale and this panel surfaces that — the fix is a
// re-extract, which is why it's called out next to that button.
//
// A session song has one stem per mic, so it can have several vocal tracks —
// and the bucket named `vocals` is just whichever mic came first, often not the
// singer. The "Transcribe" dropdown lists the song's stems (GET
// .../lyrics/vocal-tracks) with every vocal-named one ticked by default; the
// ticked ones are mixed and transcribed together. Nothing ticked means the full
// mix, which the backend separates itself.
// ---------------------------------------------------------------------------

interface LyricsPanelProps {
  songId: number;
}

type ExtractStatus = 'idle' | 'running' | 'complete' | 'failed';

interface VocalTrack {
  id: number;
  name: string;
  display_name: string | null;
  instruments: { label: string; score: number }[];
  silent: boolean;
  default: boolean;
}

function trackLabel(track: VocalTrack): string {
  return track.display_name?.trim() || track.name;
}

export default function LyricsPanel({ songId }: LyricsPanelProps) {
  const [lyrics, setLyrics] = useState('');
  const [savedLyrics, setSavedLyrics] = useState('');
  const [timings, setTimings] = useState<LyricTimings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [extractStatus, setExtractStatus] = useState<ExtractStatus>('idle');
  const [tracks, setTracks] = useState<VocalTrack[]>([]);
  const [selectedTracks, setSelectedTracks] = useState<Set<number>>(new Set());
  const [trackMenuOpen, setTrackMenuOpen] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const trackMenuRef = useRef<HTMLDivElement | null>(null);

  const dirty = lyrics !== savedLyrics;

  // The track list is a nicety: without it, extraction still runs on the
  // backend's default picks, so a failed load just hides the dropdown.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/api/produce/songs/${songId}/lyrics/vocal-tracks`);
        if (!res.ok) return;
        const data = await res.json();
        if (cancelled) return;
        const list: VocalTrack[] = data.tracks ?? [];
        setTracks(list);
        setSelectedTracks(new Set(list.filter((t) => t.default).map((t) => t.id)));
      } catch {
        // Leave the dropdown hidden.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [songId]);

  useEffect(() => {
    if (!trackMenuOpen) return;
    const close = (e: MouseEvent) => {
      if (trackMenuRef.current && !trackMenuRef.current.contains(e.target as Node)) {
        setTrackMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [trackMenuOpen]);

  const toggleTrack = (id: number) => {
    setSelectedTracks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const chosenTracks = tracks.filter((t) => selectedTracks.has(t.id));
  const trackSummary =
    chosenTracks.length === 0
      ? 'Full mix (auto-separated)'
      : chosenTracks.map(trackLabel).join(' + ');

  const loadLyrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/produce/songs/${songId}/lyrics`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load lyrics');
      setLyrics(data.lyrics || '');
      setSavedLyrics(data.lyrics || '');
      setTimings(data.timings ?? null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [songId]);

  useEffect(() => {
    loadLyrics();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [loadLyrics]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`/api/produce/songs/${songId}/lyrics`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lyrics }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save');
      setSavedLyrics(data.lyrics ?? lyrics);
      setLyrics(data.lyrics ?? lyrics);
      setTimings(data.timings ?? null);
      setMessage('Saved.');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const pollExtract = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/produce/songs/${songId}/lyrics/extract/status`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Status check failed');
        if (data.status === 'complete') {
          if (pollRef.current) clearInterval(pollRef.current);
          setExtractStatus('complete');
          setMessage('Extraction complete — lyrics updated.');
          await loadLyrics();
        } else if (data.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          setExtractStatus('failed');
          setError(data.error || 'Extraction failed');
        }
      } catch (err: any) {
        if (pollRef.current) clearInterval(pollRef.current);
        setExtractStatus('failed');
        setError(err.message);
      }
    }, 3000);
  }, [songId, loadLyrics]);

  const handleReextract = async () => {
    if (dirty && !window.confirm('Re-extracting will overwrite your unsaved edits. Continue?')) {
      return;
    }
    setError(null);
    setMessage(null);
    try {
      // Only send a choice when there was one to make; otherwise the backend
      // falls back to its own defaults.
      const res = await fetch(`/api/produce/songs/${songId}/lyrics/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: tracks.length > 0 ? JSON.stringify({ stem_ids: chosenTracks.map((t) => t.id) }) : undefined,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start extraction');
      setExtractStatus('running');
      setMessage('Transcribing… this can take a few minutes.');
      pollExtract();
    } catch (err: any) {
      setError(err.message);
    }
  };

  if (loading) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Loading lyrics…</p>;
  }

  const busy = saving || extractStatus === 'running';

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          View and edit the transcribed lyrics. Saving re-indexes them for lyric search.
          Re-extract runs speech-to-text on the song&apos;s vocal tracks.
        </p>
      </div>

      {error && (
        <div className="p-3 mb-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
          {error}
        </div>
      )}
      {message && !error && (
        <div className="p-3 mb-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 rounded-lg text-sm">
          {message}
        </div>
      )}

      <textarea
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        disabled={busy}
        rows={16}
        placeholder="No lyrics yet — type them here, or click Re-extract to transcribe from the audio."
        className="w-full text-sm font-mono rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-gray-900 dark:text-white"
      />

      <div className="flex flex-wrap items-center gap-3 mt-3">
        <button
          onClick={handleSave}
          disabled={busy || !dirty}
          className="text-sm px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          onClick={handleReextract}
          disabled={busy}
          className="text-sm px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          {extractStatus === 'running' ? 'Transcribing…' : 'Re-extract from audio'}
        </button>
        {tracks.length > 0 && (
          <div ref={trackMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setTrackMenuOpen((open) => !open)}
              disabled={busy}
              aria-haspopup="listbox"
              aria-expanded={trackMenuOpen}
              title="Which tracks to transcribe"
              className="text-sm px-3 py-2 max-w-xs truncate border border-gray-300 dark:border-gray-600 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
            >
              From: {trackSummary} ▾
            </button>
            {trackMenuOpen && (
              <div
                role="listbox"
                aria-multiselectable="true"
                className="absolute z-20 mt-1 w-72 max-h-72 overflow-y-auto rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-lg py-1"
              >
                {tracks.map((track) => (
                  <label
                    key={track.id}
                    className="flex items-start gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                  >
                    <input
                      type="checkbox"
                      checked={selectedTracks.has(track.id)}
                      onChange={() => toggleTrack(track.id)}
                      className="h-4 w-4 mt-0.5"
                    />
                    <span className="min-w-0">
                      <span className="block text-gray-900 dark:text-white truncate">
                        {trackLabel(track)}
                        {track.display_name && (
                          <span className="text-gray-500 dark:text-gray-400"> · {track.name}</span>
                        )}
                      </span>
                      {(track.instruments.length > 0 || track.silent) && (
                        <span className="block text-xs text-gray-500 dark:text-gray-400 truncate">
                          {track.silent
                            ? 'Silent'
                            : track.instruments.slice(0, 3).map((i) => i.label).join(' · ')}
                        </span>
                      )}
                    </span>
                  </label>
                ))}
                <p className="px-3 pt-1.5 pb-1 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700 mt-1">
                  Ticked tracks are mixed and transcribed together. Untick all to use the full mix.
                </p>
              </div>
            )}
          </div>
        )}
        {dirty && !busy && (
          <span className="text-xs text-amber-600 dark:text-amber-400">Unsaved changes</span>
        )}
      </div>

      <p className="text-xs mt-3 text-gray-500 dark:text-gray-400">
        {!timings ? (
          <>No follow-along timings yet — re-extract to generate them.</>
        ) : timings.status === 'stale' ? (
          <span className="text-amber-600 dark:text-amber-400">
            Follow-along timings are out of date (the lyrics were edited after
            extraction) and are hidden during playback. Re-extract to refresh them.
          </span>
        ) : (
          <>
            Follow-along timings: {timings.lines.length} lines
            {timings.audio_source === 'vocals_stem' ? ' (from isolated vocals)' : ' (from the full mix)'}.
          </>
        )}
      </p>
    </div>
  );
}
