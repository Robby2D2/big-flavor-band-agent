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
 *
 * A row whose buffer changes mid-play — a fix toggled ON/OFF, a render landing —
 * is swapped in place: the new buffer starts at the same sample on the same
 * clock and crossfades over a few ms, so an A/B toggle is heard at once with
 * no gap or restart.
 */

/** Long enough to hide the click of a cut, short enough to hear as instant. */
const SWAP_FADE_SECONDS = 0.015;

interface Voice {
  src: AudioBufferSourceNode;
  /** Per-source fade, under the row's gain, so a swap can crossfade. */
  fade: GainNode;
  buffer: AudioBuffer;
}
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

  const voicesRef = useRef<Map<number, Voice>>(new Map());
  // Swapped-out sources still fading; stopped with the rest on a teardown.
  const retiringRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const gainsRef = useRef<Map<number, GainNode>>(new Map());
  const longestDurRef = useRef(0);
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
    const sources = [
      ...Array.from(voicesRef.current.values()).map((v) => v.src),
      ...Array.from(retiringRef.current),
    ];
    for (const src of sources) {
      try {
        src.onended = null;
        src.stop();
      } catch {
        // already stopped
      }
    }
    voicesRef.current.clear();
    retiringRef.current.clear();
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
      let longestDur = 0;

      for (const stem of stems) {
        const buffer = buffers[stem.id];
        if (!buffer || offset >= buffer.duration) continue;
        const gain = ctx.createGain();
        gain.gain.value = effectiveGain(stem.id);
        gain.connect(ctx.destination);
        gainsRef.current.set(stem.id, gain);
        voicesRef.current.set(stem.id, startVoice(ctx, buffer, gain, startAt, offset, false));
        longestDur = Math.max(longestDur, buffer.duration);
      }

      if (!voicesRef.current.size) return;
      originRef.current = startAt - offset;
      longestDurRef.current = longestDur;
      playingRef.current = true;
      setPlaying(true);
      movePlayhead(offset);

      // The end of the song is found here rather than by a source's `onended`,
      // which a swap would fire early when it stops the source it replaces.
      const tick = () => {
        const t = ctx.currentTime - originRef.current;
        movePlayhead(Math.min(longestDurRef.current, Math.max(0, t)));
        if (t >= longestDurRef.current) {
          stop();
          return;
        }
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    },
    [stems, buffers, maxDuration, effectiveGain, teardown, stop, movePlayhead]
  );

  // Swap in any row whose buffer changed while playing, at the playhead.
  useEffect(() => {
    if (!playingRef.current) return;
    const ctx = getAudioContext();
    const at = ctx.currentTime + 0.01;
    const offset = at - originRef.current;
    for (const stem of stems) {
      const buffer = buffers[stem.id];
      const voice = voicesRef.current.get(stem.id);
      if (voice?.buffer === buffer) continue;
      if (voice) {
        retire(voice, at, retiringRef.current);
        voicesRef.current.delete(stem.id);
      }
      if (!buffer || offset >= buffer.duration) continue;
      let gain = gainsRef.current.get(stem.id);
      if (!gain) {
        // A row whose audio landed after play started gets its channel now.
        gain = ctx.createGain();
        gain.gain.value = effectiveGain(stem.id);
        gain.connect(ctx.destination);
        gainsRef.current.set(stem.id, gain);
      }
      voicesRef.current.set(stem.id, startVoice(ctx, buffer, gain, at, offset, true));
      longestDurRef.current = Math.max(longestDurRef.current, buffer.duration);
    }
    // Only a change of buffers is a swap; mute/solo/gain are applied above
    // without touching the sources.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buffers]);

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

/** Start one row's source at `offset` into its buffer, optionally fading in. */
function startVoice(
  ctx: AudioContext,
  buffer: AudioBuffer,
  gain: GainNode,
  at: number,
  offset: number,
  fadeIn: boolean
): Voice {
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  const fade = ctx.createGain();
  if (fadeIn) {
    fade.gain.setValueAtTime(0, at);
    fade.gain.linearRampToValueAtTime(1, at + SWAP_FADE_SECONDS);
  }
  src.connect(fade).connect(gain);
  src.start(at, offset);
  return { src, fade, buffer };
}

/** Fade a swapped-out source to silence and stop it once it is inaudible. */
function retire(voice: Voice, at: number, retiring: Set<AudioBufferSourceNode>) {
  const { src, fade } = voice;
  src.onended = () => retiring.delete(src);
  fade.gain.setValueAtTime(1, at);
  fade.gain.linearRampToValueAtTime(0, at + SWAP_FADE_SECONDS);
  try {
    src.stop(at + SWAP_FADE_SECONDS);
  } catch {
    // already stopped
  }
  retiring.add(src);
}
