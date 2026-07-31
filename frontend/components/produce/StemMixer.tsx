'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import WaveformView from './WaveformView';
import { decodeAudio, formatTime, getAudioContext } from './audioEngine';

interface Stem {
  id: number;
  name: string;
}

interface StemSet {
  id: number;
  status: string;
  model: string;
  created_at: string | null;
  error?: string | null;
  stems: Stem[];
}

interface StemControl {
  gain: number;
  mute: boolean;
  solo: boolean;
}

interface StemMixerProps {
  songId: number;
  onApplied: () => void;
}

const WAVE_COLORS = ['#60a5fa', '#34d399', '#f472b6', '#fbbf24', '#a78bfa', '#f87171'];

// A separation job is in flight while its set sits in either of these states.
const IN_FLIGHT = new Set(['queued', 'running']);

/**
 * Per-stem waveform rows with mute / solo / gain and sample-synced group
 * playback through the single shared AudioContext, plus a per-row "play this
 * stem alone" audition, a "Separate into stems" trigger that kicks off a
 * background Demucs job and polls it to completion, and a "save mix as version"
 * entry point into the existing versioning flow (issues #67 / #70).
 */
export default function StemMixer({ songId, onApplied }: StemMixerProps) {
  const [stemSet, setStemSet] = useState<StemSet | null>(null);
  const [allSets, setAllSets] = useState<StemSet[]>([]);
  const [buffers, setBuffers] = useState<Record<number, AudioBuffer>>({});
  const [controls, setControls] = useState<Record<number, StemControl>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [auditionId, setAuditionId] = useState<number | null>(null);
  const [separating, setSeparating] = useState(false);
  const [separateError, setSeparateError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const gainsRef = useRef<Map<number, GainNode>>(new Map());
  const auditionRef = useRef<AudioBufferSourceNode | null>(null);
  const startTimeRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  // The set whose stems are currently decoded, so polling doesn't re-decode.
  const loadedSetIdRef = useRef<number | null>(null);

  const activeJob = useMemo(
    () => allSets.find((s) => IN_FLIGHT.has(s.status)) || null,
    [allSets]
  );

  // A failed job worth surfacing: only when nothing is running and it's newer
  // than whatever complete set we're showing (so a fixed re-run hides it).
  const failedJob = useMemo(() => {
    if (activeJob) return null;
    const failed = allSets
      .filter((s) => s.status === 'failed')
      .sort((a, b) => b.id - a.id)[0];
    if (!failed) return null;
    if (stemSet && stemSet.id > failed.id) return null;
    return failed;
  }, [allSets, activeJob, stemSet]);

  const maxDuration = useMemo(
    () => Object.values(buffers).reduce((m, b) => Math.max(m, b.duration), 0),
    [buffers]
  );

  const anySolo = useMemo(
    () => Object.values(controls).some((c) => c.solo),
    [controls]
  );

  const effectiveGain = useCallback(
    (id: number): number => {
      const c = controls[id];
      if (!c || c.mute) return 0;
      if (anySolo && !c.solo) return 0;
      return c.gain;
    },
    [controls, anySolo]
  );

  const stopPlayback = useCallback(() => {
    for (const src of sourcesRef.current) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        // already stopped
      }
    }
    sourcesRef.current = [];
    gainsRef.current.clear();
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    setPlaying(false);
    setPlayhead(0);
  }, []);

  const stopAudition = useCallback(() => {
    if (auditionRef.current) {
      try {
        auditionRef.current.onended = null;
        auditionRef.current.stop();
      } catch {
        // already stopped
      }
      auditionRef.current = null;
    }
    setAuditionId(null);
  }, []);

  // Fetch the song's stem sets; decode the latest completed one if it's new.
  // `isCancelled` lets an in-flight load bail out when the song changes.
  const loadStems = useCallback(
    async (isCancelled: () => boolean): Promise<void> => {
      const res = await fetch(`/api/produce/songs/${songId}/stems`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load stems');
      if (isCancelled()) return;

      const sets: StemSet[] = data.stem_sets || [];
      setAllSets(sets);

      const complete = sets
        .filter((s) => s.status === 'complete' && s.stems.length > 0)
        .sort((a, b) => b.id - a.id);
      const chosen = complete[0] || null;

      if (!chosen) {
        loadedSetIdRef.current = null;
        setStemSet(null);
        setBuffers({});
        return;
      }
      if (chosen.id === loadedSetIdRef.current) return; // already decoded

      const decoded: Record<number, AudioBuffer> = {};
      const nextControls: Record<number, StemControl> = {};
      for (const stem of chosen.stems) {
        decoded[stem.id] = await decodeAudio(`/api/produce/stems/${stem.id}/audio`);
        nextControls[stem.id] = { gain: 1, mute: false, solo: false };
      }
      if (isCancelled()) return;
      loadedSetIdRef.current = chosen.id;
      setStemSet(chosen);
      setBuffers(decoded);
      setControls(nextControls);
    },
    [songId]
  );

  // Initial load (and reload) whenever the song changes.
  useEffect(() => {
    let cancelled = false;
    stopPlayback();
    stopAudition();
    loadedSetIdRef.current = null;
    setLoading(true);
    setError(null);
    setSeparateError(null);
    setStemSet(null);
    setAllSets([]);
    setBuffers({});

    loadStems(() => cancelled)
      .catch((err) => {
        if (!cancelled) setError((err as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [songId, loadStems, stopPlayback, stopAudition]);

  // Poll while a separation job is queued/running, until it settles.
  useEffect(() => {
    if (!activeJob) return;
    let cancelled = false;
    const id = setInterval(() => {
      loadStems(() => cancelled).catch(() => {
        // Transient poll failures are non-fatal; the next tick retries.
      });
    }, 4000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeJob, loadStems]);

  // Stop everything on unmount.
  useEffect(() => {
    return () => {
      stopPlayback();
      stopAudition();
    };
  }, [stopPlayback, stopAudition]);

  // Live-apply gain/mute/solo changes to already-playing (group) nodes.
  useEffect(() => {
    if (!playing) return;
    const ctx = getAudioContext();
    for (const [id, node] of gainsRef.current) {
      node.gain.setTargetAtTime(effectiveGain(id), ctx.currentTime, 0.01);
    }
  }, [controls, playing, effectiveGain]);

  const startPlayback = useCallback(async () => {
    if (!stemSet) return;
    const ctx = getAudioContext();
    await ctx.resume();
    stopAudition();
    stopPlayback();

    const startAt = ctx.currentTime + 0.05;
    const sources: AudioBufferSourceNode[] = [];
    let longest: AudioBufferSourceNode | null = null;
    let longestDur = 0;

    for (const stem of stemSet.stems) {
      const buffer = buffers[stem.id];
      if (!buffer) continue;
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      const gain = ctx.createGain();
      gain.gain.value = effectiveGain(stem.id);
      src.connect(gain).connect(ctx.destination);
      src.start(startAt);
      sources.push(src);
      gainsRef.current.set(stem.id, gain);
      if (buffer.duration > longestDur) {
        longestDur = buffer.duration;
        longest = src;
      }
    }

    if (!sources.length) return;
    sourcesRef.current = sources;
    startTimeRef.current = startAt;
    if (longest) longest.onended = () => stopPlayback();
    setPlaying(true);

    const tick = () => {
      const t = ctx.currentTime - startTimeRef.current;
      setPlayhead(Math.max(0, t));
      if (t >= longestDur) {
        stopPlayback();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [stemSet, buffers, effectiveGain, stopPlayback, stopAudition]);

  // Play a single stem in isolation (independent of the group transport).
  const toggleAudition = useCallback(
    async (id: number) => {
      const ctx = getAudioContext();
      await ctx.resume();
      if (auditionId === id) {
        stopAudition();
        return;
      }
      stopPlayback();
      stopAudition();
      const buffer = buffers[id];
      if (!buffer) return;
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      src.onended = () => {
        auditionRef.current = null;
        setAuditionId(null);
      };
      src.start();
      auditionRef.current = src;
      setAuditionId(id);
    },
    [auditionId, buffers, stopAudition, stopPlayback]
  );

  const setControl = (id: number, patch: Partial<StemControl>) => {
    setControls((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  const handleSeparate = async () => {
    setSeparating(true);
    setSeparateError(null);
    try {
      const res = await fetch('/api/produce/stems/separate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to start separation');
      // Refresh so the queued job shows immediately; the poll effect takes over.
      await loadStems(() => false);
    } catch (err) {
      setSeparateError((err as Error).message);
    } finally {
      setSeparating(false);
    }
  };

  const handleSaveMix = async () => {
    if (!stemSet) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      // Solo is resolved to mute for the render: soloing a stem silences the rest.
      const adjustments: Record<string, { gain: number; mute: boolean }> = {};
      for (const stem of stemSet.stems) {
        const c = controls[stem.id];
        if (!c) continue;
        const muted = c.mute || (anySolo && !c.solo);
        adjustments[stem.name] = { gain: c.gain, mute: muted };
      }
      const res = await fetch(`/api/produce/stems/${stemSet.id}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adjustments }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save mix');
      setSaveMsg('Saved the current stem mix as a new candidate version below.');
      onApplied();
    } catch (err) {
      setSaveMsg(`Error: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">Loading stems…</p>
    );
  }
  if (error) {
    return <p className="text-sm text-red-600 dark:text-red-400">{error}</p>;
  }

  // Separation controls sit above the mixer so a song with no stems yet can be
  // separated, and a song that already has stems can be re-separated.
  const separationControls = (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={handleSeparate}
          disabled={separating || activeJob != null}
          className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {stemSet ? 'Re-separate into stems' : 'Separate into stems'}
        </button>
        {activeJob ? (
          <span className="inline-flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <span className="h-3 w-3 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
            Separating stems ({activeJob.status})… this takes a few minutes. You
            can leave this page and come back.
          </span>
        ) : (
          <span className="text-xs text-gray-500 dark:text-gray-400 max-w-md">
            Splits this song into vocals, drums, bass, guitar, piano, and other
            with Demucs. The originals are never touched.
          </span>
        )}
      </div>
      {separateError && (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{separateError}</p>
      )}
      {failedJob && (
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">
          The last separation failed{failedJob.error ? `: ${failedJob.error}` : '.'} You
          can try again above.
        </p>
      )}
    </div>
  );

  if (!stemSet) {
    return (
      <div>
        {separationControls}
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {activeJob
            ? 'Once separation finishes, each part appears here with its own waveform, mute / solo / gain, and synced playback.'
            : 'No stems for this song yet. Separate it into stems above to get a per-part mixer with its own waveform, mute / solo / gain, and synced playback.'}
        </p>
      </div>
    );
  }

  return (
    <div>
      {separationControls}

      <div className="flex items-center gap-3 mb-4">
        <button
          onClick={playing ? stopPlayback : startPlayback}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          {playing ? 'Stop' : 'Play stems'}
        </button>
        <span className="text-sm text-gray-500 dark:text-gray-400 tabular-nums">
          {formatTime(playhead)} / {formatTime(maxDuration)}
        </span>
        <button
          onClick={handleSaveMix}
          disabled={saving}
          className="ml-auto px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400"
        >
          {saving ? 'Saving…' : 'Save mix as new version'}
        </button>
      </div>

      {saveMsg && (
        <p className="text-sm mb-3 text-gray-700 dark:text-gray-300">{saveMsg}</p>
      )}

      <div className="space-y-3">
        {stemSet.stems.map((stem, i) => {
          const c = controls[stem.id];
          const silenced = effectiveGain(stem.id) === 0;
          const auditioning = auditionId === stem.id;
          return (
            <div
              key={stem.id}
              className={`border border-gray-200 dark:border-gray-700 rounded-lg p-3 ${
                silenced ? 'opacity-50' : ''
              }`}
            >
              <div className="flex items-center gap-3 mb-2">
                <span className="w-20 text-sm font-medium capitalize text-gray-800 dark:text-gray-200">
                  {stem.name}
                </span>
                <button
                  onClick={() => toggleAudition(stem.id)}
                  title="Play this stem on its own"
                  className={`text-xs px-2 py-1 rounded border ${
                    auditioning
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  {auditioning ? '■ Stop' : '▶ Play alone'}
                </button>
                <button
                  onClick={() => setControl(stem.id, { mute: !c?.mute })}
                  className={`text-xs px-2 py-1 rounded border ${
                    c?.mute
                      ? 'bg-red-600 text-white border-red-600'
                      : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  Mute
                </button>
                <button
                  onClick={() => setControl(stem.id, { solo: !c?.solo })}
                  className={`text-xs px-2 py-1 rounded border ${
                    c?.solo
                      ? 'bg-yellow-500 text-white border-yellow-500'
                      : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300'
                  }`}
                >
                  Solo
                </button>
                <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 ml-2">
                  Gain
                  <input
                    type="range"
                    min={0}
                    max={1.5}
                    step={0.05}
                    value={c?.gain ?? 1}
                    onChange={(e) =>
                      setControl(stem.id, { gain: Number(e.target.value) })
                    }
                  />
                  <span className="w-8 tabular-nums">
                    {(c?.gain ?? 1).toFixed(2)}
                  </span>
                </label>
              </div>
              <WaveformView
                buffer={buffers[stem.id] ?? null}
                duration={maxDuration}
                height={64}
                playhead={playing ? playhead : null}
                waveColor={WAVE_COLORS[i % WAVE_COLORS.length]}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
