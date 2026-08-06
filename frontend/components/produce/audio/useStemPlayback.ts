'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getAudioContext } from '../audioEngine';

export interface StemPlaybackControl {
  gain: number;
  mute: boolean;
  solo: boolean;
}

/**
 * Sample-synced group playback through the single shared AudioContext
 * (extracted from the old StemMixer, which owned this same engine inline).
 * Every stem plays through one AudioContext clock, which is what keeps
 * mute/solo/gain and multi-stem sync accurate.
 *
 * Transport is media-player shaped: play/pause keeps the playhead where it is
 * and `seek` moves it, restarting every source at the new offset so the stems
 * stay sample-synced across a scrub.
 */
export function useStemPlayback(
  stems: { id: number; name: string }[],
  buffers: Record<number, AudioBuffer>,
  controls: Record<number, StemPlaybackControl>,
  /**
   * Song length as reported by the server's waveform envelopes, so the
   * timeline exists before any audio has been decoded.
   */
  durationHint = 0
) {
  const [playing, setPlaying] = useState(false);
  const [playhead, setPlayhead] = useState(0);

  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const gainsRef = useRef<Map<number, GainNode>>(new Map());
  /** ctx.currentTime that corresponds to playhead 0 (start time minus offset). */
  const originRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const playheadRef = useRef(0);
  const playingRef = useRef(false);

  // max() rather than preferring the hint: playback still works if the
  // envelopes failed to load, and a lossy playback copy that decodes a few ms
  // longer than the source can't truncate the transport.
  const maxDuration = useMemo(
    () =>
      Math.max(
        durationHint,
        Object.values(buffers).reduce((m, b) => Math.max(m, b.duration), 0)
      ),
    [buffers, durationHint]
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

  const movePlayhead = useCallback((t: number) => {
    playheadRef.current = t;
    setPlayhead(t);
  }, []);

  /** Tear the graph down without touching the playhead (pause/seek/stop share it). */
  const teardown = useCallback(() => {
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
    playingRef.current = false;
    setPlaying(false);
  }, []);

  const pause = useCallback(() => {
    teardown();
  }, [teardown]);

  const stop = useCallback(() => {
    teardown();
    movePlayhead(0);
  }, [teardown, movePlayhead]);

  // Live-apply gain/mute/solo changes to already-playing nodes.
  useEffect(() => {
    if (!playing) return;
    const ctx = getAudioContext();
    for (const [id, node] of gainsRef.current) {
      node.gain.setTargetAtTime(effectiveGain(id), ctx.currentTime, 0.01);
    }
  }, [controls, playing, effectiveGain]);

  const play = useCallback(
    async (from?: number) => {
      if (!stems.length) return;
      const ctx = getAudioContext();
      await ctx.resume();
      teardown();

      // Playing from the very end (or past it) restarts the track, the way a
      // media player's play button does after it has run out.
      const requested = from ?? playheadRef.current;
      const offset = requested >= maxDuration - 0.05 ? 0 : Math.max(0, requested);

      const startAt = ctx.currentTime + 0.05;
      const sources: AudioBufferSourceNode[] = [];
      let longest: AudioBufferSourceNode | null = null;
      let longestDur = 0;

      for (const stem of stems) {
        const buffer = buffers[stem.id];
        if (!buffer || offset >= buffer.duration) continue;
        const src = ctx.createBufferSource();
        src.buffer = buffer;
        const gain = ctx.createGain();
        gain.gain.value = effectiveGain(stem.id);
        src.connect(gain).connect(ctx.destination);
        src.start(startAt, offset);
        sources.push(src);
        gainsRef.current.set(stem.id, gain);
        if (buffer.duration > longestDur) {
          longestDur = buffer.duration;
          longest = src;
        }
      }

      if (!sources.length) return;
      sourcesRef.current = sources;
      originRef.current = startAt - offset;
      if (longest) longest.onended = () => stop();
      playingRef.current = true;
      setPlaying(true);
      movePlayhead(offset);

      const tick = () => {
        const t = ctx.currentTime - originRef.current;
        movePlayhead(Math.min(longestDur, Math.max(0, t)));
        if (t >= longestDur) {
          stop();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [stems, buffers, maxDuration, effectiveGain, teardown, stop, movePlayhead]
  );

  /** Jump to a position; resumes from there if a playback pass is running. */
  const seek = useCallback(
    (seconds: number) => {
      const clamped = Math.min(Math.max(0, seconds), maxDuration);
      if (playingRef.current) {
        void play(clamped);
      } else {
        movePlayhead(clamped);
      }
    },
    [maxDuration, play, movePlayhead]
  );

  const toggle = useCallback(() => {
    if (playingRef.current) pause();
    else void play();
  }, [pause, play]);

  useEffect(() => () => teardown(), [teardown]);

  return { playing, playhead, maxDuration, play, pause, stop, seek, toggle };
}
