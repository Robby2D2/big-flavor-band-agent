'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import WaveformView from './WaveformView';
import StemMixer from './StemMixer';
import { decodeAudio, formatTime, Region } from './audioEngine';

interface MultitrackEditorProps {
  songId: number;
  /** The version whose audio is loaded into the editor (the working source). */
  sourceVersionId: number | null;
  /** Called after Apply creates a new candidate version, to refresh the list. */
  onApplied: () => void;
}

type ToolKey = 'trim' | 'noise_reduction' | 'pitch' | 'tempo' | 'eq';

const TOOLS: { key: ToolKey; label: string; help: string }[] = [
  { key: 'trim', label: 'Trim to selection', help: 'Keep only the selected span, discarding audio outside it.' },
  { key: 'noise_reduction', label: 'Reduce noise', help: 'Remove steady background noise from the selection (or sample it as the noise profile).' },
  { key: 'pitch', label: 'Pitch correction', help: 'Key-aware auto-tune over the selection; strength is the retune amount.' },
  { key: 'tempo', label: 'Tempo / beat correction', help: 'Quantize beats to a steady tempo. Whole-file by design; strength is the correction amount.' },
  { key: 'eq', label: 'EQ / cleanup', help: 'Apply EQ (high-pass, low-pass, and a boost band) over the selection.' },
];

// Whole-file tools ignore the region; the rest require a selection to act on.
const WHOLE_FILE_TOOLS: ToolKey[] = ['tempo'];

interface ToolParams {
  // pitch
  key?: string;
  chromatic?: boolean;
  // tempo
  target_bpm?: number;
  // noise_reduction
  non_stationary?: boolean;
  noise_from_selection?: boolean;
  // eq
  high_pass_freq?: number;
  low_pass_freq?: number;
  boost_freq?: number;
  boost_db?: number;
}

/**
 * Full-mix waveform region editor (issue #70): draw-select a region, pick a
 * tool + strength + tool-specific controls, Preview the processed region A/B
 * against the original (no version created), then Apply to create a new
 * candidate version that enters the existing audition/approve/publish flow.
 */
export default function MultitrackEditor({
  songId,
  sourceVersionId,
  onApplied,
}: MultitrackEditorProps) {
  const [buffer, setBuffer] = useState<AudioBuffer | null>(null);
  const [duration, setDuration] = useState(0);
  const [beats, setBeats] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [region, setRegion] = useState<Region | null>(null);
  const [tool, setTool] = useState<ToolKey>('trim');
  const [strength, setStrength] = useState(0.8);
  const [params, setParams] = useState<ToolParams>({});

  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [playhead, setPlayhead] = useState<number | null>(null);
  const originalAudioRef = useRef<HTMLAudioElement>(null);

  const sourceAudioUrl =
    sourceVersionId != null
      ? `/api/produce/versions/${sourceVersionId}/audio`
      : null;

  // Load + decode the working source audio and its beat markers whenever the
  // selected version changes.
  useEffect(() => {
    if (sourceVersionId == null) return;
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    setBuffer(null);
    setRegion(null);
    setPreviewPath(null);
    setMessage(null);

    (async () => {
      try {
        const decoded = await decodeAudio(
          `/api/produce/versions/${sourceVersionId}/audio`
        );
        if (cancelled) return;
        setBuffer(decoded);
        setDuration(decoded.duration);
      } catch (err) {
        if (!cancelled) setLoadError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    (async () => {
      try {
        const res = await fetch(
          `/api/produce/songs/${songId}/beats?source_version_id=${sourceVersionId}`
        );
        const data = await res.json();
        if (!cancelled && res.ok) setBeats(data.beats || []);
      } catch {
        // Beat markers are optional — absence must not break the editor.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [songId, sourceVersionId]);

  const isWholeFile = WHOLE_FILE_TOOLS.includes(tool);
  const needsRegion = !isWholeFile;
  const hasRegion = region != null && region.end - region.start > 0.01;
  const canRun =
    sourceVersionId != null &&
    buffer != null &&
    busy == null &&
    (!needsRegion || hasRegion);

  const setParam = (patch: Partial<ToolParams>) =>
    setParams((prev) => ({ ...prev, ...patch }));

  const buildRequestBody = useCallback(() => {
    // Region bounds: whole-file tools omit them. Noise "sample from selection"
    // sends the region as the noise profile and denoises the whole file.
    const start = isWholeFile ? null : region?.start ?? null;
    const end = isWholeFile ? null : region?.end ?? null;

    const outParams: Record<string, unknown> = {};
    if (tool === 'pitch') {
      if (params.key) outParams.key = params.key;
      if (params.chromatic) outParams.chromatic = true;
    } else if (tool === 'tempo') {
      if (params.target_bpm) outParams.target_bpm = params.target_bpm;
    } else if (tool === 'noise_reduction') {
      if (params.non_stationary) outParams.non_stationary = true;
    } else if (tool === 'eq') {
      if (params.high_pass_freq != null) outParams.high_pass_freq = params.high_pass_freq;
      if (params.low_pass_freq != null) outParams.low_pass_freq = params.low_pass_freq;
      if (params.boost_freq != null) outParams.boost_freq = params.boost_freq;
      if (params.boost_db != null) outParams.boost_db = params.boost_db;
    }

    let startOut = start;
    let endOut = end;
    if (tool === 'noise_reduction' && params.noise_from_selection && region) {
      outParams.noise_start_s = region.start;
      outParams.noise_end_s = region.end;
      // Sample noise from the selection but denoise the whole file.
      startOut = null;
      endOut = null;
    }

    return {
      song_id: songId,
      source_version_id: sourceVersionId,
      tool,
      start_s: startOut,
      end_s: endOut,
      strength,
      params: outParams,
    };
  }, [isWholeFile, region, tool, params, songId, sourceVersionId, strength]);

  const handlePreview = async () => {
    setBusy('preview');
    setMessage(null);
    setPreviewPath(null);
    try {
      const res = await fetch('/api/produce/region/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Preview failed');
      setPreviewPath(data.candidate_path);
      setMessage('Preview ready — compare it against the original below. No version was created.');
    } catch (err) {
      setMessage(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const handleApply = async () => {
    setBusy('apply');
    setMessage(null);
    try {
      const res = await fetch('/api/produce/region/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildRequestBody()),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Apply failed');
      setMessage('Applied — saved as a new candidate version below.');
      setPreviewPath(null);
      onApplied();
    } catch (err) {
      setMessage(`Error: ${(err as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  if (sourceVersionId == null) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Select a starting version above to load the waveform editor.
      </p>
    );
  }

  return (
    <div>
      {loading && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Loading waveform…</p>
      )}
      {loadError && (
        <p className="text-sm text-red-600 dark:text-red-400 mb-3">{loadError}</p>
      )}

      <WaveformView
        buffer={buffer}
        duration={duration}
        selectable
        region={region}
        onRegionChange={setRegion}
        beats={beats}
        playhead={playhead}
      />

      <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-gray-600 dark:text-gray-400">
        <span>
          {region
            ? `Selection: ${formatTime(region.start)} – ${formatTime(region.end)}`
            : 'Drag on the waveform to select a region.'}
        </span>
        {region && (
          <button
            onClick={() => setRegion(null)}
            className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            Clear selection
          </button>
        )}
        {beats.length > 0 && (
          <span className="text-xs text-yellow-600 dark:text-yellow-400">
            {beats.length} beat markers
          </span>
        )}
      </div>

      {/* Original playback drives the waveform playhead. */}
      {sourceAudioUrl && (
        <audio
          ref={originalAudioRef}
          controls
          preload="none"
          src={sourceAudioUrl}
          className="mt-3 h-9 w-full max-w-md"
          onTimeUpdate={(e) => setPlayhead(e.currentTarget.currentTime)}
          onPause={() => setPlayhead(null)}
          onEnded={() => setPlayhead(null)}
        />
      )}

      {/* Tool panel */}
      <div className="mt-5 border-t border-gray-200 dark:border-gray-700 pt-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Tool
            </label>
            <select
              value={tool}
              onChange={(e) => {
                setTool(e.target.value as ToolKey);
                setPreviewPath(null);
                setMessage(null);
              }}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
            >
              {TOOLS.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {TOOLS.find((t) => t.key === tool)?.help}
            </p>
          </div>

          {tool !== 'trim' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Strength (wet/dry): {strength.toFixed(2)}
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={strength}
                onChange={(e) => setStrength(Number(e.target.value))}
                className="w-full"
              />
            </div>
          )}
        </div>

        {/* Tool-specific controls */}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {tool === 'pitch' && (
            <>
              <label className="text-sm text-gray-700 dark:text-gray-300">
                Key override (optional)
                <input
                  type="text"
                  placeholder="e.g. A minor"
                  value={params.key ?? ''}
                  onChange={(e) => setParam({ key: e.target.value || undefined })}
                  className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 mt-6">
                <input
                  type="checkbox"
                  checked={!!params.chromatic}
                  onChange={(e) => setParam({ chromatic: e.target.checked })}
                />
                Chromatic (snap to nearest semitone)
              </label>
            </>
          )}

          {tool === 'tempo' && (
            <label className="text-sm text-gray-700 dark:text-gray-300">
              Target BPM (optional)
              <input
                type="number"
                min={40}
                max={240}
                value={params.target_bpm ?? ''}
                onChange={(e) =>
                  setParam({
                    target_bpm: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
              />
            </label>
          )}

          {tool === 'noise_reduction' && (
            <>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={!!params.non_stationary}
                  onChange={(e) => setParam({ non_stationary: e.target.checked })}
                />
                Non-stationary (adaptive) reduction
              </label>
              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input
                  type="checkbox"
                  checked={!!params.noise_from_selection}
                  disabled={!hasRegion}
                  onChange={(e) => setParam({ noise_from_selection: e.target.checked })}
                />
                Use selection as the noise profile (denoise whole file)
              </label>
            </>
          )}

          {tool === 'eq' && (
            <>
              <label className="text-sm text-gray-700 dark:text-gray-300">
                High-pass (Hz)
                <input
                  type="number"
                  value={params.high_pass_freq ?? ''}
                  onChange={(e) =>
                    setParam({ high_pass_freq: e.target.value ? Number(e.target.value) : undefined })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </label>
              <label className="text-sm text-gray-700 dark:text-gray-300">
                Low-pass (Hz)
                <input
                  type="number"
                  value={params.low_pass_freq ?? ''}
                  onChange={(e) =>
                    setParam({ low_pass_freq: e.target.value ? Number(e.target.value) : undefined })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </label>
              <label className="text-sm text-gray-700 dark:text-gray-300">
                Boost frequency (Hz)
                <input
                  type="number"
                  value={params.boost_freq ?? ''}
                  onChange={(e) =>
                    setParam({ boost_freq: e.target.value ? Number(e.target.value) : undefined })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </label>
              <label className="text-sm text-gray-700 dark:text-gray-300">
                Boost amount (dB)
                <input
                  type="number"
                  value={params.boost_db ?? ''}
                  onChange={(e) =>
                    setParam({ boost_db: e.target.value ? Number(e.target.value) : undefined })
                  }
                  className="mt-1 w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                />
              </label>
            </>
          )}
        </div>

        {needsRegion && !hasRegion && (
          <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">
            This tool needs a region — drag on the waveform to select one.
          </p>
        )}

        <div className="flex flex-wrap items-center gap-3 mt-4">
          <button
            onClick={handlePreview}
            disabled={!canRun}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {busy === 'preview' ? 'Previewing…' : 'Preview'}
          </button>
          <button
            onClick={handleApply}
            disabled={!canRun}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {busy === 'apply' ? 'Applying…' : 'Apply as new version'}
          </button>
        </div>

        {message && (
          <p className="mt-3 text-sm text-gray-700 dark:text-gray-300">{message}</p>
        )}

        {previewPath && (
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Original
              </p>
              {sourceAudioUrl && (
                <audio controls preload="none" src={sourceAudioUrl} className="h-9 w-full" />
              )}
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Preview (processed)
              </p>
              <audio
                controls
                preload="none"
                src={`/api/produce/clean/preview?path=${encodeURIComponent(previewPath)}`}
                className="h-9 w-full"
              />
            </div>
          </div>
        )}
      </div>

      {/* Per-stem rows (only render once stems exist for the song). */}
      <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3">
          Stems
        </h3>
        <StemMixer songId={songId} onApplied={onApplied} />
      </div>
    </div>
  );
}
