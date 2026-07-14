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

/**
 * Per-stem waveform rows with mute / solo / gain and sample-synced playback
 * through the single shared AudioContext, plus a "save mix as version" entry
 * point into the existing versioning flow (issue #70). Rendering stems that
 * already exist — kicking off separation is out of scope.
 */
export default function StemMixer({ songId, onApplied }: StemMixerProps) {
  const [stemSet, setStemSet] = useState<StemSet | null>(null);
  const [buffers, setBuffers] = useState<Record<number, AudioBuffer>>({});
  const [controls, setControls] = useState<Record<number, StemControl>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const gainsRef = useRef<Map<number, GainNode>>(new Map());
  const startTimeRef = useRef(0);
  const rafRef = useRef<number | null>(null);

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

  // Load the latest completed stem set and decode its stems.
  useEffect(() => {
    let cancelled = false;
    stopPlayback();
    setLoading(true);
    setError(null);
    setStemSet(null);
    setBuffers({});

    (async () => {
      try {
        const res = await fetch(`/api/produce/songs/${songId}/stems`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to load stems');
        const sets: StemSet[] = data.stem_sets || [];
        const complete = sets
          .filter((s) => s.status === 'complete' && s.stems.length > 0)
          .sort((a, b) => b.id - a.id);
        const chosen = complete[0] || null;
        if (cancelled) return;
        setStemSet(chosen);
        if (!chosen) {
          setLoading(false);
          return;
        }

        const decoded: Record<number, AudioBuffer> = {};
        const nextControls: Record<number, StemControl> = {};
        for (const stem of chosen.stems) {
          decoded[stem.id] = await decodeAudio(
            `/api/produce/stems/${stem.id}/audio`
          );
          nextControls[stem.id] = { gain: 1, mute: false, solo: false };
        }
        if (cancelled) return;
        setBuffers(decoded);
        setControls(nextControls);
      } catch (err) {
        if (!cancelled) setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [songId]);

  // Stop everything on unmount.
  useEffect(() => stopPlayback, [stopPlayback]);

  // Live-apply gain/mute/solo changes to already-playing nodes.
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
  }, [stemSet, buffers, effectiveGain, stopPlayback]);

  const setControl = (id: number, patch: Partial<StemControl>) => {
    setControls((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
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
    return (
      <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
    );
  }
  if (!stemSet) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No stems for this song yet. Once its stems have been separated, each part
        appears here with its own waveform, mute / solo / gain, and synced
        playback.
      </p>
    );
  }

  return (
    <div>
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
