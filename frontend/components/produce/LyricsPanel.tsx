'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// Lyrics tab: view / hand-edit / re-extract a song's lyrics.
//
// Reads GET /api/produce/songs/{id}/lyrics, saves edits via PUT (which re-embeds
// so lyric search stays consistent), and can kick off a background Whisper
// re-extraction (POST .../lyrics/extract) that it polls to completion, then
// reloads the freshly transcribed text.
// ---------------------------------------------------------------------------

interface LyricsPanelProps {
  songId: number;
}

type ExtractStatus = 'idle' | 'running' | 'complete' | 'failed';

export default function LyricsPanel({ songId }: LyricsPanelProps) {
  const [lyrics, setLyrics] = useState('');
  const [savedLyrics, setSavedLyrics] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [extractStatus, setExtractStatus] = useState<ExtractStatus>('idle');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const dirty = lyrics !== savedLyrics;

  const loadLyrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/produce/songs/${songId}/lyrics`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load lyrics');
      setLyrics(data.lyrics || '');
      setSavedLyrics(data.lyrics || '');
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
      const res = await fetch(`/api/produce/songs/${songId}/lyrics/extract`, { method: 'POST' });
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
          Re-extract runs speech-to-text on the original audio.
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
        {dirty && !busy && (
          <span className="text-xs text-amber-600 dark:text-amber-400">Unsaved changes</span>
        )}
      </div>
    </div>
  );
}
