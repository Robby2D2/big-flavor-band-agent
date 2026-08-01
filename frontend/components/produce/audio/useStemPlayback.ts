'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getAudioContext } from '../audioEngine';

export interface StemPlaybackControl {
  gain: number;
  mute: boolean;
  solo: boolean;
}

/**
 * Sample-synced group playback + per-stem audition through the single shared
 * AudioContext (extracted from the old StemMixer, which owned this same
 * engine inline). Every stem plays through one AudioContext clock, which is
 * what keeps mute/solo/gain and multi-stem sync accurate.
 */
export function useStemPlayback(
  stems: { id: number; name: string }[],
  buffers: Record<number, AudioBuffer>,
  controls: Record<number, StemPlaybackControl>
) {
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);
  const [auditionId, setAuditionId] = useState<number | null>(null);

  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const gainsRef = useRef<Map<number, GainNode>>(new Map());
  const auditionRef = useRef<AudioBufferSourceNode | null>(null);
  const startTimeRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  const maxDuration = useMemo(
    () => Object.values(buffers).reduce((m, b) => Math.max(m, b.duration), 0),
    [buffers]
  );

  const anySolo = useMemo(() => Object.values(controls).some((c) => c.solo), [controls]);

  const effectiveGain = useCallback(
    (id: number): number => {
      const c = controls[id];
      if (!c || c.mute) return 0;
      if (anySolo && !c.solo) return 0;
      return c.gain;
    },
    [controls, anySolo]
  );

  const stop = useCallback(() => {
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

  // Live-apply gain/mute/solo changes to already-playing (group) nodes.
  useEffect(() => {
    if (!playing) return;
    const ctx = getAudioContext();
    for (const [id, node] of gainsRef.current) {
      node.gain.setTargetAtTime(effectiveGain(id), ctx.currentTime, 0.01);
    }
  }, [controls, playing, effectiveGain]);

  const start = useCallback(async () => {
    if (!stems.length) return;
    const ctx = getAudioContext();
    await ctx.resume();
    stopAudition();
    stop();

    const startAt = ctx.currentTime + 0.05;
    const sources: AudioBufferSourceNode[] = [];
    let longest: AudioBufferSourceNode | null = null;
    let longestDur = 0;

    for (const stem of stems) {
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
    if (longest) longest.onended = () => stop();
    setPlaying(true);

    const tick = () => {
      const t = ctx.currentTime - startTimeRef.current;
      setPlayhead(Math.max(0, t));
      if (t >= longestDur) {
        stop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, [stems, buffers, effectiveGain, stop, stopAudition]);

  const toggleAudition = useCallback(
    async (id: number) => {
      const ctx = getAudioContext();
      await ctx.resume();
      if (auditionId === id) {
        stopAudition();
        return;
      }
      stop();
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
    [auditionId, buffers, stop, stopAudition]
  );

  useEffect(
    () => () => {
      stop();
      stopAudition();
    },
    [stop, stopAudition]
  );

  return { playing, playhead, maxDuration, auditionId, start, stop, toggleAudition };
}
