'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { computePeaks, Region } from './audioEngine';

interface WaveformViewProps {
  buffer: AudioBuffer | null;
  duration: number;
  height?: number;
  /** Enable drag-to-select. When false the waveform is display-only (stem rows). */
  selectable?: boolean;
  region?: Region | null;
  onRegionChange?: (region: Region | null) => void;
  /**
   * The detected "keep" span (e.g. analysis's detected_music_start/end).
   * The area outside it is shaded red to show what trimming would remove.
   */
  trimRegion?: Region | null;
  /** Beat times (seconds) drawn as faint vertical markers. */
  beats?: number[];
  /** Current playback position (seconds), drawn as a moving line. */
  playhead?: number | null;
  waveColor?: string;
}

const DEFAULT_WAVE = '#60a5fa';

/**
 * Canvas waveform with optional drag region-select, beat markers, and a
 * playhead. Peaks are computed from the AudioBuffer itself (no external lib), so
 * the same component draws the full mix and each stem row (issue #70).
 */
export default function WaveformView({
  buffer,
  duration,
  height = 96,
  selectable = false,
  region = null,
  onRegionChange,
  trimRegion = null,
  beats,
  playhead = null,
  waveColor = DEFAULT_WAVE,
}: WaveformViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(600);
  const dragAnchor = useRef<number | null>(null);

  // Track the container width so peaks and hit-testing use the rendered size.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => setWidth(el.clientWidth || 600);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const peaks = useMemo(
    () => (buffer ? computePeaks(buffer, width) : null),
    [buffer, width]
  );

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const mid = height / 2;

    // Trim-away zones (drawn under everything else): shade the parts of the
    // clip outside the detected "keep" span in red, with a boundary marker
    // at each cut point.
    if (trimRegion && duration > 0) {
      const xStart = (trimRegion.start / duration) * width;
      const xEnd = (trimRegion.end / duration) * width;
      ctx.fillStyle = 'rgba(239, 68, 68, 0.16)';
      if (xStart > 0) ctx.fillRect(0, 0, xStart, height);
      if (xEnd < width) ctx.fillRect(xEnd, 0, width - xEnd, height);
      ctx.fillStyle = 'rgba(239, 68, 68, 0.9)';
      if (xStart > 0) ctx.fillRect(Math.max(0, xStart - 1.5), 0, 1.5, height);
      if (xEnd < width) ctx.fillRect(xEnd, 0, 1.5, height);
    }

    // Region highlight (drawn under the waveform).
    if (region && duration > 0) {
      const x1 = (region.start / duration) * width;
      const x2 = (region.end / duration) * width;
      ctx.fillStyle = 'rgba(96, 165, 250, 0.22)';
      ctx.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1), height);
      ctx.fillStyle = 'rgba(96, 165, 250, 0.9)';
      ctx.fillRect(Math.min(x1, x2), 0, 1.5, height);
      ctx.fillRect(Math.max(x1, x2) - 1.5, 0, 1.5, height);
    }

    // Waveform peaks.
    if (peaks) {
      ctx.fillStyle = waveColor;
      for (let x = 0; x < peaks.width; x++) {
        const yHi = mid - peaks.max[x] * mid;
        const yLo = mid - peaks.min[x] * mid;
        ctx.fillRect(x, yHi, 1, Math.max(1, yLo - yHi));
      }
    } else {
      ctx.fillStyle = 'rgba(148,163,184,0.4)';
      ctx.fillRect(0, mid - 1, width, 2);
    }

    // Beat markers.
    if (beats && beats.length && duration > 0) {
      ctx.fillStyle = 'rgba(250, 204, 21, 0.35)';
      for (const t of beats) {
        const x = (t / duration) * width;
        ctx.fillRect(x, 0, 1, height);
      }
    }

    // Playhead.
    if (playhead != null && duration > 0) {
      const x = (playhead / duration) * width;
      ctx.fillStyle = '#ef4444';
      ctx.fillRect(x, 0, 1.5, height);
    }
  }, [peaks, width, height, region, trimRegion, duration, beats, playhead, waveColor]);

  const xToTime = useCallback(
    (clientX: number): number => {
      const rect = canvasRef.current?.getBoundingClientRect();
      if (!rect || rect.width === 0) return 0;
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
      return ratio * duration;
    },
    [duration]
  );

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!selectable || !onRegionChange || duration <= 0) return;
    (e.target as HTMLCanvasElement).setPointerCapture(e.pointerId);
    const t = xToTime(e.clientX);
    dragAnchor.current = t;
    onRegionChange({ start: t, end: t });
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!selectable || !onRegionChange || dragAnchor.current == null) return;
    const t = xToTime(e.clientX);
    const anchor = dragAnchor.current;
    onRegionChange({ start: Math.min(anchor, t), end: Math.max(anchor, t) });
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!selectable || !onRegionChange || dragAnchor.current == null) return;
    const t = xToTime(e.clientX);
    const anchor = dragAnchor.current;
    dragAnchor.current = null;
    // A click with no meaningful drag clears the selection.
    if (Math.abs(t - anchor) < duration * 0.005) {
      onRegionChange(null);
    } else {
      onRegionChange({ start: Math.min(anchor, t), end: Math.max(anchor, t) });
    }
  };

  return (
    <div ref={containerRef} className="w-full">
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height }}
        className={`rounded bg-gray-100 dark:bg-gray-900 ${
          selectable ? 'cursor-crosshair' : ''
        }`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      />
    </div>
  );
}
