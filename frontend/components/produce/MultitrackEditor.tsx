'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import WaveformView from './WaveformView';
import StemMixer from './StemMixer';
import { Meter, BalanceBar, MeterTone } from './IssueMeter';
import { decodeAudio, formatTime, Region } from './audioEngine';

interface VersionOption {
  id: number;
  name: string;
  is_published: boolean;
}

interface MultitrackEditorProps {
  songId: number;
  /** Versions available to start from; the editor owns which one is active. */
  versions: VersionOption[];
  /** Called after a new candidate version is created, to refresh the list. */
  onApplied: () => void;
}

type SelectionMode = 'whole' | 'region';
type Intensity = 'gentle' | 'moderate' | 'aggressive';
type StepKey = 'trim' | 'noise_reduction' | 'eq' | 'pitch' | 'tempo' | 'normalize' | 'master';

interface EqBand {
  frequency: number;
  gain_db: number;
}

interface TrimParams {
  threshold_db: number;
}
interface NoiseParams {
  reduction_strength: number;
  noise_profile_duration: number;
  non_stationary: boolean;
}
interface EqParams {
  high_pass_freq?: number;
  low_pass_freq?: number;
  bands: EqBand[];
}
interface NormalizeParams {
  target_peak_db: number;
  apply_compression: boolean;
  compression_ratio: number;
}
interface MasterParams {
  target_lufs: number;
}
interface PitchParams {
  correction_strength: number;
  key?: string;
  chromatic: boolean;
}
interface TempoParams {
  target_bpm?: number;
}

interface StepParamsState {
  trim: TrimParams;
  noise_reduction: NoiseParams;
  eq: EqParams;
  pitch: PitchParams;
  tempo: TempoParams;
  normalize: NormalizeParams;
  master: MasterParams;
}

const DEFAULT_STEP_PARAMS: StepParamsState = {
  trim: { threshold_db: -40 },
  noise_reduction: { reduction_strength: 0.6, noise_profile_duration: 1.0, non_stationary: false },
  eq: { bands: [] },
  pitch: { correction_strength: 1.0, chromatic: false },
  tempo: {},
  normalize: { target_peak_db: -3, apply_compression: true, compression_ratio: 2.5 },
  master: { target_lufs: -14 },
};

// Whole-song-only steps: peak normalization and integrated-loudness mastering
// both look at the whole track, so they never scope to a region — running
// them on a slice would shift the level/loudness of audio outside it too
// (issue #77 follow-up).
const STEP_DEFS: {
  key: StepKey;
  label: string;
  help: string;
  hasIntensity: boolean;
  wholeSongOnly: boolean;
}[] = [
  {
    key: 'trim',
    label: 'Trim non-musical content',
    help: 'Cuts silence, noise, or talking detected at the edges of the selection, so it begins and finishes on the music.',
    hasIntensity: false,
    wholeSongOnly: false,
  },
  {
    key: 'noise_reduction',
    label: 'Reduce noise',
    help: 'Removes steady background noise such as hiss, hum, or room tone.',
    hasIntensity: true,
    wholeSongOnly: false,
  },
  {
    key: 'eq',
    label: 'Apply EQ corrections',
    help: 'Balances the frequencies: filters out low rumble, tames a boomy or muddy low end, and adds clarity (or softens harsh highs).',
    hasIntensity: true,
    wholeSongOnly: false,
  },
  {
    key: 'pitch',
    label: 'Pitch correction',
    help: 'Key-aware auto-tune over the selection: detects (or uses a chosen) key and nudges off-key notes back toward it. Has its own retune strength, separate from Intensity.',
    hasIntensity: false,
    wholeSongOnly: false,
  },
  {
    key: 'tempo',
    label: 'Tempo / beat correction',
    help: 'Time-stretches the whole track to a target tempo without changing pitch. Whole-track only, so it only appears in Whole song mode.',
    hasIntensity: false,
    wholeSongOnly: true,
  },
  {
    key: 'normalize',
    label: 'Normalize',
    help: 'Raises the track to a consistent volume and evens out the loud and quiet parts with compression, toward the target peak below.',
    hasIntensity: true,
    wholeSongOnly: true,
  },
  {
    key: 'master',
    label: 'Master',
    help: 'A final polish that brings the track to the target loudness below, so it sits well alongside other songs.',
    hasIntensity: false,
    wholeSongOnly: true,
  },
];

// Mirrors auto_clean_recording's own aggressiveness multipliers, so picking a
// preset in the UI previews exactly what gets sent as an explicit step_params
// override.
const MULT: Record<Intensity, number> = { gentle: 0.7, moderate: 1.0, aggressive: 1.3 };

const inputClass =
  'mt-1 w-full px-2 py-1.5 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm';

function InfoTip({ text, label }: { text: string; label: string }) {
  return (
    <span
      title={text}
      aria-label={`${label}: ${text}`}
      tabIndex={0}
      className="inline-flex items-center justify-center h-4 w-4 rounded-full border border-gray-400 dark:border-gray-500 text-[10px] font-semibold leading-none text-gray-500 dark:text-gray-400 cursor-help select-none focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      i
    </span>
  );
}

// Reads the backend's analyze recommendations into the steps_override map
// used by both the manual flow and the one-click shortcut.
function stepsFromAnalysis(result: any): Record<string, boolean> {
  const recs = result?.recommendations;
  if (!recs) return {};
  return {
    trim: !!recs.trim?.recommended,
    noise_reduction: !!recs.noise_reduction?.recommended,
    eq: !!recs.eq?.recommended,
    normalize: recs.normalization?.recommended ?? true,
    master: recs.mastering?.recommended ?? true,
  };
}

// The agent's suggested gentle/moderate/aggressive preset per step, straight
// from the analysis's own measurements (noise floor, EQ correction count,
// crest factor) — see analyze_and_recommend_processing's recommended_intensity.
function intensityFromAnalysis(result: any): Partial<Record<StepKey, Intensity>> {
  const recs = result?.recommendations;
  if (!recs) return {};
  return {
    noise_reduction: recs.noise_reduction?.recommended_intensity ?? 'moderate',
    eq: recs.eq?.recommended_intensity ?? 'moderate',
    normalize: recs.normalization?.recommended_intensity ?? 'moderate',
  };
}

function noiseParamsForIntensity(recs: any, intensity: Intensity): NoiseParams {
  const base = recs?.noise_reduction?.recommended_strength ?? 0.6;
  return {
    reduction_strength: Math.min(1, Math.max(0, base * MULT[intensity])),
    noise_profile_duration: recs?.noise_reduction?.recommended_profile_duration ?? 1.0,
    non_stationary: false,
  };
}

function eqParamsForIntensity(recs: any, intensity: Intensity): EqParams {
  const adjustments = recs?.eq?.adjustments ?? [];
  let high_pass_freq: number | undefined;
  let low_pass_freq: number | undefined;
  const bands: EqBand[] = [];
  for (const adj of adjustments) {
    if (adj.type === 'high_pass') high_pass_freq = adj.frequency;
    else if (adj.type === 'low_pass') low_pass_freq = adj.frequency;
    else if (adj.type === 'boost' || adj.type === 'reduce') {
      bands.push({ frequency: adj.frequency, gain_db: Math.round(adj.amount * MULT[intensity] * 10) / 10 });
    }
  }
  return { high_pass_freq, low_pass_freq, bands };
}

function normalizeParamsForIntensity(recs: any, intensity: Intensity): NormalizeParams {
  let ratio = recs?.compression?.ratio ?? 2.5;
  if (intensity === 'aggressive') ratio *= 1.2;
  else if (intensity === 'gentle') ratio *= 0.8;
  return {
    target_peak_db: recs?.normalization?.target_peak_db ?? -3,
    apply_compression: true,
    compression_ratio: Math.round(ratio * 100) / 100,
  };
}

function masterParamsFromAnalysis(recs: any): MasterParams {
  return { target_lufs: recs?.mastering?.target_lufs ?? -14 };
}

// Maps a UI step to its registry tool + the params payload the per-tool
// /api/produce/tools/{tool}/apply endpoint expects (param NAMES must match the
// tool's declared Params). Returns null when a required value is missing (e.g.
// tempo with no target BPM). Region bounds are sent separately by the caller.
const STEP_TO_TOOL: Record<StepKey, string> = {
  trim: 'trim_silence',
  noise_reduction: 'reduce_noise',
  eq: 'apply_eq',
  pitch: 'correct_pitch',
  tempo: 'match_tempo',
  normalize: 'normalize_audio',
  master: 'apply_mastering',
};

function paramsForStep(stepKey: StepKey, sp: StepParamsState): Record<string, any> | null {
  switch (stepKey) {
    case 'trim':
      return { threshold_db: sp.trim.threshold_db };
    case 'noise_reduction':
      return {
        reduction_strength: sp.noise_reduction.reduction_strength,
        noise_profile_duration: sp.noise_reduction.noise_profile_duration,
        non_stationary: sp.noise_reduction.non_stationary,
      };
    case 'eq':
      return {
        ...(sp.eq.high_pass_freq != null ? { high_pass_freq: sp.eq.high_pass_freq } : {}),
        ...(sp.eq.low_pass_freq != null ? { low_pass_freq: sp.eq.low_pass_freq } : {}),
        eq_bands: sp.eq.bands,
      };
    case 'pitch':
      return {
        auto_tune: true,
        correction_strength: sp.pitch.correction_strength,
        chromatic: sp.pitch.chromatic,
        ...(sp.pitch.key ? { key: sp.pitch.key } : {}),
      };
    case 'tempo':
      return sp.tempo.target_bpm ? { target_bpm: sp.tempo.target_bpm } : null;
    case 'normalize':
      return {
        target_level_db: sp.normalize.target_peak_db,
        apply_compression: sp.normalize.apply_compression,
        compression_ratio: sp.normalize.compression_ratio,
      };
    case 'master':
      return { target_loudness: sp.master.target_lufs };
    default:
      return {};
  }
}

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x));
}

// Scales for each meter's track. These mirror the thresholds the backend
// uses to flag a recommendation (analyze_and_recommend_processing), so the
// meter fill and its color band line up with when a step actually fires.
function noiseMeterProps(recs: any) {
  const db = recs?.noise_reduction?.noise_level_db;
  if (db == null) return null;
  const min = -60;
  const max = -20;
  const tone: MeterTone = db > -40 ? 'critical' : db > -50 ? 'warning' : 'ok';
  return { fraction: clamp01((db - min) / (max - min)), tone, valueLabel: `${db.toFixed(1)} dB` };
}

function normalizationMeterProps(recs: any, targetOverride?: number) {
  const peak = recs?.normalization?.current_peak_db;
  const target = targetOverride ?? recs?.normalization?.target_peak_db ?? -3;
  if (peak == null) return null;
  const min = -24;
  const max = 0;
  const tone: MeterTone = peak > -1 ? 'critical' : peak < -6 ? 'warning' : 'ok';
  return {
    fraction: clamp01((peak - min) / (max - min)),
    target: clamp01((target - min) / (max - min)),
    tone,
    valueLabel: `${peak.toFixed(1)} dB (target ${target.toFixed(0)})`,
  };
}

function masteringMeterProps(recs: any, targetOverride?: number) {
  const lufs = recs?.mastering?.current_lufs_measured;
  const target = targetOverride ?? recs?.mastering?.target_lufs ?? -14;
  if (lufs == null) return null;
  const min = -32;
  const max = -8;
  const tone: MeterTone =
    lufs > -10 ? 'critical' : Math.abs(lufs - target) <= 2 ? 'ok' : 'warning';
  return {
    fraction: clamp01((lufs - min) / (max - min)),
    target: clamp01((target - min) / (max - min)),
    tone,
    valueLabel: `${lufs.toFixed(1)} LUFS (target ${target.toFixed(0)})`,
  };
}

// The inline finding shown inside each tool's card — the analysis reason plus
// that tool's small graph — folded in from the old standalone "Detected issues"
// list so each detection lives with the control that acts on it. Target-bearing
// meters read the *current* edited target so the tick moves live as the user
// tunes Normalize/Master. Trim's detection is the red zones on the waveform.
function stepFindingNode(stepKey: StepKey, recs: any, stepParams: StepParamsState) {
  if (!recs) return null;
  if (stepKey === 'trim') {
    if (!recs.trim?.recommended) return null;
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {recs.trim.reason} — shown as the red zones on the waveform above.
      </p>
    );
  }
  if (stepKey === 'noise_reduction') {
    const m = noiseMeterProps(recs);
    return (
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {recs.noise_reduction?.reason}
        {m && <Meter valueLabel={m.valueLabel} fraction={m.fraction} tone={m.tone} />}
      </div>
    );
  }
  if (stepKey === 'eq') {
    const fb = recs.eq?.frequency_balance;
    const n = recs.eq?.adjustments?.length ?? 0;
    return (
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {recs.eq?.recommended ? `${n} frequency imbalance(s) detected` : 'Frequency balance looks fine'}
        {fb && <BalanceBar bass={fb.bass_percent} mid={fb.mid_percent} treble={fb.treble_percent} />}
      </div>
    );
  }
  if (stepKey === 'normalize') {
    const m = normalizationMeterProps(recs, stepParams.normalize.target_peak_db);
    return (
      <div className="text-xs text-gray-500 dark:text-gray-400">
        {recs.normalization?.reason}
        {m && <Meter valueLabel={m.valueLabel} fraction={m.fraction} target={m.target} tone={m.tone} />}
      </div>
    );
  }
  if (stepKey === 'master') {
    const m = masteringMeterProps(recs, stepParams.master.target_lufs);
    return m ? (
      <div className="text-xs text-gray-500 dark:text-gray-400">
        <Meter valueLabel={m.valueLabel} fraction={m.fraction} target={m.target} tone={m.tone} />
      </div>
    ) : null;
  }
  return null; // pitch / tempo have no analysis-backed finding
}

/**
 * Unified audio-processing panel for the produce page (issue #77): one
 * starting-version picker, a shared waveform, and a "Whole song" / "Region"
 * selection mode — both drive the *same* analyze -> detected issues ->
 * per-step controls -> Preview/Clean pipeline. A region is a scope, not a
 * different tool: Trim/Reduce noise/EQ/Pitch correction confine themselves to
 * it; Normalize, Master, and Tempo/beat correction (whole-track operations)
 * only appear in Whole song mode. Every step's controls are agent-prefilled
 * from the analysis where a measurement backs them, and individually tunable
 * down to the raw parameter — Pitch and Tempo have no analysis measurement
 * behind them (issue #82) so they render with sensible defaults instead,
 * fully manual. A "Clean this version" shortcut runs
 * the whole-song analyze+clean in one action for non-power users. Per-stem
 * rows remain available underneath.
 */
export default function MultitrackEditor({
  songId,
  versions,
  onApplied,
}: MultitrackEditorProps) {
  const [sourceVersionId, setSourceVersionId] = useState<number | null>(null);
  // Region is implicit: a non-empty waveform selection *is* the region; with no
  // selection the tools act on the whole song. `selectionMode` is derived from
  // that (below) so the existing whole/region logic keeps working unchanged.

  const [buffer, setBuffer] = useState<AudioBuffer | null>(null);
  const [duration, setDuration] = useState(0);
  const [beats, setBeats] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [region, setRegion] = useState<Region | null>(null);

  const [analysis, setAnalysis] = useState<any>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [stepEnabled, setStepEnabled] = useState<Record<string, boolean>>({});
  const [stepIntensity, setStepIntensity] = useState<Partial<Record<StepKey, Intensity>>>({});
  const [stepParams, setStepParams] = useState<StepParamsState>(DEFAULT_STEP_PARAMS);

  const [busy, setBusy] = useState<'preview' | 'clean' | null>(null);
  const [runResult, setRunResult] = useState<any>(null);
  const [previewCandidatePath, setPreviewCandidatePath] = useState<string | null>(null);

  // Per-tool Apply (one tool -> one new version), independent of the global Clean.
  const [stepApply, setStepApply] = useState<Partial<Record<StepKey, 'busy' | null>>>({});
  const [stepApplyMsg, setStepApplyMsg] = useState<
    Partial<Record<StepKey, { kind: 'ok' | 'err'; text: string } | null>>
  >({});

  // One-click shortcut state — independent of the manual flow above.
  const [quickCleaning, setQuickCleaning] = useState(false);
  const [quickMessage, setQuickMessage] = useState<string | null>(null);

  const [playhead, setPlayhead] = useState<number | null>(null);
  const originalAudioRef = useRef<HTMLAudioElement>(null);

  // Default the working source to the published version, else the first one,
  // and keep it if it's still present after a version list refresh.
  useEffect(() => {
    setSourceVersionId((prev) => {
      if (prev != null && versions.some((v) => v.id === prev)) return prev;
      const published = versions.find((v) => v.is_published);
      return published?.id ?? versions[0]?.id ?? null;
    });
  }, [versions]);

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
    setAnalysis(null);
    setRunResult(null);
    setPreviewCandidatePath(null);
    setQuickMessage(null);

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

  const hasRegion = region != null && region.end - region.start > 0.01;
  const selectionMode: SelectionMode = hasRegion ? 'region' : 'whole';
  const visibleSteps = STEP_DEFS.filter((s) => selectionMode === 'whole' || !s.wholeSongOnly);
  const analysisOk = analysis && analysis.status === 'success';

  const setStepIntensityFor = (step: StepKey, intensity: Intensity) => {
    setStepIntensity((prev) => ({ ...prev, [step]: intensity }));
    const recs = analysis?.recommendations;
    if (!recs) return;
    if (step === 'noise_reduction') {
      setStepParams((prev) => ({ ...prev, noise_reduction: noiseParamsForIntensity(recs, intensity) }));
    } else if (step === 'eq') {
      setStepParams((prev) => ({ ...prev, eq: eqParamsForIntensity(recs, intensity) }));
    } else if (step === 'normalize') {
      setStepParams((prev) => ({ ...prev, normalize: normalizeParamsForIntensity(recs, intensity) }));
    }
  };

  function patchStepParams<K extends StepKey>(step: K, patch: Partial<StepParamsState[K]>) {
    setStepParams((prev) => ({ ...prev, [step]: { ...prev[step], ...patch } }));
  }

  const toggleStep = (key: string) => {
    setStepEnabled((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const seedFromAnalysis = (result: any) => {
    setStepEnabled(stepsFromAnalysis(result));
    const intensity = intensityFromAnalysis(result);
    setStepIntensity(intensity);
    const recs = result?.recommendations;
    if (recs) {
      setStepParams({
        trim: { threshold_db: -40 },
        noise_reduction: noiseParamsForIntensity(recs, intensity.noise_reduction ?? 'moderate'),
        eq: eqParamsForIntensity(recs, intensity.eq ?? 'moderate'),
        // No analysis measurement backs pitch/tempo — sensible defaults only
        // (issue #82), fully manually tunable below.
        pitch: DEFAULT_STEP_PARAMS.pitch,
        tempo: DEFAULT_STEP_PARAMS.tempo,
        normalize: normalizeParamsForIntensity(recs, intensity.normalize ?? 'moderate'),
        master: masterParamsFromAnalysis(recs),
      });
    }
  };

  const handleAnalyze = async () => {
    if (sourceVersionId == null) return;
    if (selectionMode === 'region' && !hasRegion) return;
    setAnalyzing(true);
    setAnalysis(null);
    setRunResult(null);
    setPreviewCandidatePath(null);
    try {
      const response = await fetch('/api/produce/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          source_version_id: sourceVersionId,
          start_s: selectionMode === 'region' ? region?.start ?? null : null,
          end_s: selectionMode === 'region' ? region?.end ?? null : null,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Analysis failed');
      }
      setAnalysis(data.result);
      seedFromAnalysis(data.result);
    } catch (err: any) {
      setAnalysis({ status: 'error', error: err.message });
    } finally {
      setAnalyzing(false);
    }
  };

  const buildStepParamsPayload = useCallback((): Record<string, unknown> => {
    const out: Record<string, unknown> = {};
    if (selectionMode === 'region' && stepEnabled.trim) {
      out.trim = { threshold_db: stepParams.trim.threshold_db };
    }
    if (stepEnabled.noise_reduction) {
      out.noise_reduction = stepParams.noise_reduction;
    }
    if (stepEnabled.eq) {
      out.eq = {
        high_pass_freq: stepParams.eq.high_pass_freq,
        low_pass_freq: stepParams.eq.low_pass_freq,
        bands: stepParams.eq.bands,
      };
    }
    if (stepEnabled.pitch) {
      out.pitch = {
        correction_strength: stepParams.pitch.correction_strength,
        chromatic: stepParams.pitch.chromatic,
        ...(stepParams.pitch.key ? { key: stepParams.pitch.key } : {}),
      };
    }
    if (selectionMode === 'whole') {
      out.normalize = stepParams.normalize;
      out.master = stepParams.master;
      if (stepEnabled.tempo && stepParams.tempo.target_bpm) {
        out.tempo = { target_bpm: stepParams.tempo.target_bpm };
      }
    }
    return out;
  }, [selectionMode, stepEnabled, stepParams]);

  const runClean = async (preview: boolean) => {
    if (sourceVersionId == null) return;
    if (selectionMode === 'region' && !hasRegion) return;
    setBusy(preview ? 'preview' : 'clean');
    setRunResult(null);
    if (!preview) setPreviewCandidatePath(null);
    try {
      const response = await fetch('/api/produce/auto-clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          aggressiveness: 'moderate',
          steps_override: stepEnabled,
          step_params: buildStepParamsPayload(),
          source_version_id: sourceVersionId,
          start_s: selectionMode === 'region' ? region?.start ?? null : null,
          end_s: selectionMode === 'region' ? region?.end ?? null : null,
          preview,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || (preview ? 'Preview failed' : 'Clean failed'));
      }
      setRunResult(data.result);
      if (data.result?.status === 'success') {
        if (preview) {
          setPreviewCandidatePath(data.candidate_path);
        } else {
          onApplied();
        }
      }
    } catch (err: any) {
      setRunResult({ status: 'error', error: err.message });
    } finally {
      setBusy(null);
    }
  };

  // Apply a single tool (with its current params + the implicit region) as its
  // own new version, via the per-tool endpoint — distinct from the global Clean.
  const applyStep = async (stepKey: StepKey) => {
    if (sourceVersionId == null) return;
    const params = paramsForStep(stepKey, stepParams);
    if (params == null) {
      setStepApplyMsg((m) => ({ ...m, [stepKey]: { kind: 'err', text: 'Set a target BPM first.' } }));
      return;
    }
    setStepApply((s) => ({ ...s, [stepKey]: 'busy' }));
    setStepApplyMsg((m) => ({ ...m, [stepKey]: null }));
    try {
      const res = await fetch(`/api/produce/tools/${STEP_TO_TOOL[stepKey]}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          source_version_id: sourceVersionId,
          start_s: hasRegion ? region?.start ?? null : null,
          end_s: hasRegion ? region?.end ?? null : null,
          params,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Apply failed');
      setStepApplyMsg((m) => ({ ...m, [stepKey]: { kind: 'ok', text: 'Applied — new version created.' } }));
      onApplied();
    } catch (err: any) {
      setStepApplyMsg((m) => ({ ...m, [stepKey]: { kind: 'err', text: err.message } }));
    } finally {
      setStepApply((s) => ({ ...s, [stepKey]: null }));
    }
  };

  // One-click shortcut: analyze then clean the whole song with the
  // recommended steps at moderate intensity, without touching the manual
  // flow's picker state.
  const handleQuickClean = async () => {
    if (sourceVersionId == null) return;
    setQuickCleaning(true);
    setQuickMessage(null);
    try {
      const analyzeRes = await fetch('/api/produce/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, source_version_id: sourceVersionId }),
      });
      const analyzeData = await analyzeRes.json();
      if (!analyzeRes.ok) {
        throw new Error(analyzeData.error || 'Analysis failed');
      }
      const steps = stepsFromAnalysis(analyzeData.result);

      const cleanRes = await fetch('/api/produce/auto-clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          aggressiveness: 'moderate',
          steps_override: steps,
          source_version_id: sourceVersionId,
        }),
      });
      const cleanData = await cleanRes.json();
      if (!cleanRes.ok) {
        throw new Error(cleanData.error || 'Clean failed');
      }
      if (cleanData.result?.status !== 'success') {
        throw new Error(cleanData.result?.error || 'Clean failed');
      }
      setQuickMessage(
        `Success — ${cleanData.result.total_steps} step(s) applied. Saved as a new version below.`
      );
      onApplied();
    } catch (err) {
      setQuickMessage(`Error: ${(err as Error).message}`);
    } finally {
      setQuickCleaning(false);
    }
  };

  const tempoMissingTarget =
    selectionMode === 'whole' && !!stepEnabled.tempo && !stepParams.tempo.target_bpm;

  const canRun =
    sourceVersionId != null &&
    analysisOk &&
    busy == null &&
    (selectionMode === 'whole' || hasRegion) &&
    !tempoMissingTarget;

  if (versions.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No versions yet for this song.
      </p>
    );
  }

  return (
    <div>
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Starting version
        </label>
        <select
          value={sourceVersionId ?? ''}
          onChange={(e) =>
            setSourceVersionId(e.target.value ? Number(e.target.value) : null)
          }
          className="w-full max-w-md px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:border-blue-500"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
              {v.is_published ? ' (default)' : ''}
            </option>
          ))}
        </select>
      </div>

      {sourceVersionId == null ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Select a starting version above to load the editor.
        </p>
      ) : (
        <>
          {/* One-click shortcut for non-power users. */}
          <div className="flex flex-wrap items-center gap-3 mb-6 pb-6 border-b border-gray-200 dark:border-gray-700">
            <button
              onClick={handleQuickClean}
              disabled={quickCleaning}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {quickCleaning ? 'Cleaning...' : 'Clean this version'}
            </button>
            <span className="text-xs text-gray-500 dark:text-gray-400 max-w-md">
              One click: analyzes the whole starting version and applies the
              recommended steps at moderate intensity as a new version.
            </span>
            {quickMessage && (
              <span className="text-sm text-gray-700 dark:text-gray-300 basis-full">
                {quickMessage}
              </span>
            )}
          </div>

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
            trimRegion={
              selectionMode === 'whole' && analysisOk
                ? {
                    start: analysis.recommendations.trim.detected_music_start,
                    end: analysis.recommendations.trim.detected_music_end,
                  }
                : null
            }
            beats={beats}
            playhead={playhead}
          />

          {selectionMode === 'whole' && analysisOk && analysis.recommendations.trim.recommended && (
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              Red zones show the non-musical content Trim would remove.
            </p>
          )}

          {/* Region is implicit: drag selects it, "Whole song" clears it. */}
          <div className="flex flex-wrap items-center gap-3 mt-2 text-sm text-gray-600 dark:text-gray-400">
            {hasRegion ? (
              <>
                <span>
                  Selection: {formatTime(region!.start)} – {formatTime(region!.end)}
                </span>
                <button
                  onClick={() => setRegion(null)}
                  className="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                >
                  Whole song
                </button>
              </>
            ) : (
              <span>Whole song — drag on the waveform to limit tools to a region.</span>
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

          <div className="mt-5 border-t border-gray-200 dark:border-gray-700 pt-4">
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              {hasRegion
                ? 'Analyzing the selected region. Trim, Reduce noise, EQ, and Pitch correction scope to it; Normalize, Master, and Tempo are whole-track and hidden while a region is selected.'
                : 'Analyze inspects every tool and prepopulates each with recommended settings. Then tune and Clean all enabled tools into one version, or Apply a single tool.'}
            </p>

            <button
              onClick={handleAnalyze}
              disabled={analyzing || sourceVersionId == null}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
            >
              {analyzing ? 'Analyzing...' : 'Analyze all tools'}
            </button>

            {analysis && analysis.status === 'error' && (
              <div className="mt-4 p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
                {analysis.error}
              </div>
            )}
            {analysisOk && analysis.summary && (
              <p className="mt-4 text-sm text-gray-700 dark:text-gray-300">{analysis.summary}</p>
            )}

            {analysisOk && (
              <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-6 space-y-4">
                {visibleSteps.map((step) => (
                  <div
                    key={step.key}
                    className="border border-gray-200 dark:border-gray-700 rounded-lg p-3"
                  >
                    <label className="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-200">
                      <input
                        type="checkbox"
                        checked={!!stepEnabled[step.key]}
                        onChange={() => toggleStep(step.key)}
                        className="h-4 w-4"
                      />
                      {step.label}
                      <InfoTip text={step.help} label={step.label} />
                    </label>

                    {/* Folded-in detection for this tool (was the separate
                        "Detected issues" list). */}
                    <div className="mt-1 pl-6">
                      {stepFindingNode(step.key, analysis.recommendations, stepParams)}
                    </div>

                    {/* Apply just this tool as its own version. */}
                    <div className="mt-2 pl-6 flex flex-wrap items-center gap-3">
                      <button
                        onClick={() => applyStep(step.key)}
                        disabled={stepApply[step.key] === 'busy' || busy != null}
                        className="text-xs px-3 py-1 border border-blue-300 dark:border-blue-700 rounded text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-50"
                      >
                        {stepApply[step.key] === 'busy' ? 'Applying…' : 'Apply just this'}
                      </button>
                      {stepApplyMsg[step.key] && (
                        <span
                          className={`text-xs ${
                            stepApplyMsg[step.key]!.kind === 'ok'
                              ? 'text-green-600 dark:text-green-400'
                              : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {stepApplyMsg[step.key]!.text}
                        </span>
                      )}
                    </div>

                    {stepEnabled[step.key] && (
                      <div className="mt-2 pl-6 space-y-2">
                        {step.hasIntensity && (
                          <div className="flex flex-wrap items-center gap-2">
                            <label className="text-xs text-gray-600 dark:text-gray-400">
                              Intensity
                            </label>
                            <select
                              value={stepIntensity[step.key] ?? 'moderate'}
                              onChange={(e) =>
                                setStepIntensityFor(step.key, e.target.value as Intensity)
                              }
                              className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                            >
                              <option value="gentle">Gentle</option>
                              <option value="moderate">Moderate</option>
                              <option value="aggressive">Aggressive</option>
                            </select>
                            <span className="text-xs text-gray-400 dark:text-gray-500">
                              (agent suggests {intensityFromAnalysis(analysis)[step.key] ?? 'moderate'})
                            </span>
                          </div>
                        )}

                        {step.key === 'normalize' && (
                          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                            Target peak (dB)
                            <input
                              type="number"
                              step={0.5}
                              value={stepParams.normalize.target_peak_db}
                              onChange={(e) =>
                                patchStepParams('normalize', { target_peak_db: Number(e.target.value) })
                              }
                              className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            />
                          </label>
                        )}

                        {step.key === 'master' && (
                          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                            Target loudness (LUFS)
                            <input
                              type="number"
                              step={0.5}
                              value={stepParams.master.target_lufs}
                              onChange={(e) =>
                                patchStepParams('master', { target_lufs: Number(e.target.value) })
                              }
                              className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            />
                          </label>
                        )}

                        {step.key === 'pitch' && (
                          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                            Retune strength (0–1)
                            <input
                              type="number"
                              min={0}
                              max={1}
                              step={0.05}
                              value={stepParams.pitch.correction_strength}
                              onChange={(e) =>
                                patchStepParams('pitch', { correction_strength: Number(e.target.value) })
                              }
                              className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            />
                          </label>
                        )}

                        {step.key === 'tempo' && (
                          <>
                            <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
                              Target BPM
                              <input
                                type="number"
                                min={40}
                                max={240}
                                value={stepParams.tempo.target_bpm ?? ''}
                                onChange={(e) =>
                                  patchStepParams('tempo', {
                                    target_bpm: e.target.value ? Number(e.target.value) : undefined,
                                  })
                                }
                                className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                              />
                            </label>
                            {!stepParams.tempo.target_bpm && (
                              <span className="text-xs text-amber-600 dark:text-amber-400">
                                Enter a target BPM to run this step.
                              </span>
                            )}
                          </>
                        )}

                        <details className="text-xs">
                          <summary className="cursor-pointer text-gray-500 dark:text-gray-400">
                            Advanced
                          </summary>
                          <div className="mt-2 grid gap-2 sm:grid-cols-2 max-w-md">
                            {step.key === 'trim' && selectionMode === 'region' && (
                              <label className="text-gray-600 dark:text-gray-400">
                                Silence threshold (dB)
                                <input
                                  type="number"
                                  value={stepParams.trim.threshold_db}
                                  onChange={(e) =>
                                    patchStepParams('trim', { threshold_db: Number(e.target.value) })
                                  }
                                  className={inputClass}
                                />
                              </label>
                            )}
                            {step.key === 'trim' && selectionMode === 'whole' && (
                              <span className="text-gray-500 dark:text-gray-400 sm:col-span-2">
                                Whole-song trim uses the detected music span shown on the waveform above — no extra parameters.
                              </span>
                            )}

                            {step.key === 'noise_reduction' && (
                              <>
                                <label className="text-gray-600 dark:text-gray-400">
                                  Reduction strength (0–1)
                                  <input
                                    type="number"
                                    min={0}
                                    max={1}
                                    step={0.05}
                                    value={stepParams.noise_reduction.reduction_strength}
                                    onChange={(e) =>
                                      patchStepParams('noise_reduction', {
                                        reduction_strength: Number(e.target.value),
                                      })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                <label className="text-gray-600 dark:text-gray-400">
                                  Noise profile duration (s)
                                  <input
                                    type="number"
                                    min={0.1}
                                    step={0.1}
                                    value={stepParams.noise_reduction.noise_profile_duration}
                                    onChange={(e) =>
                                      patchStepParams('noise_reduction', {
                                        noise_profile_duration: Number(e.target.value),
                                      })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                <label className="flex items-center gap-2 text-gray-600 dark:text-gray-400 sm:col-span-2">
                                  <input
                                    type="checkbox"
                                    checked={stepParams.noise_reduction.non_stationary}
                                    onChange={(e) =>
                                      patchStepParams('noise_reduction', {
                                        non_stationary: e.target.checked,
                                      })
                                    }
                                  />
                                  Non-stationary (adaptive) reduction — for intermittent noise
                                </label>
                              </>
                            )}

                            {step.key === 'eq' && (
                              <>
                                <label className="text-gray-600 dark:text-gray-400">
                                  High-pass (Hz)
                                  <input
                                    type="number"
                                    value={stepParams.eq.high_pass_freq ?? ''}
                                    onChange={(e) =>
                                      patchStepParams('eq', {
                                        high_pass_freq: e.target.value ? Number(e.target.value) : undefined,
                                      })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                <label className="text-gray-600 dark:text-gray-400">
                                  Low-pass (Hz)
                                  <input
                                    type="number"
                                    value={stepParams.eq.low_pass_freq ?? ''}
                                    onChange={(e) =>
                                      patchStepParams('eq', {
                                        low_pass_freq: e.target.value ? Number(e.target.value) : undefined,
                                      })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                {stepParams.eq.bands.length > 0 ? (
                                  <div className="sm:col-span-2 space-y-1">
                                    {stepParams.eq.bands.map((band, i) => (
                                      <label
                                        key={i}
                                        className="flex items-center gap-2 text-gray-600 dark:text-gray-400"
                                      >
                                        {band.frequency} Hz band gain (dB)
                                        <input
                                          type="number"
                                          step={0.5}
                                          value={band.gain_db}
                                          onChange={(e) => {
                                            const bands = stepParams.eq.bands.slice();
                                            bands[i] = { ...bands[i], gain_db: Number(e.target.value) };
                                            patchStepParams('eq', { bands });
                                          }}
                                          className="w-24 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                        />
                                      </label>
                                    ))}
                                  </div>
                                ) : (
                                  <span className="text-gray-500 dark:text-gray-400 sm:col-span-2">
                                    No frequency imbalance detected — high-pass/low-pass only.
                                  </span>
                                )}
                              </>
                            )}

                            {step.key === 'pitch' && (
                              <>
                                <label className="text-gray-600 dark:text-gray-400">
                                  Key override (optional)
                                  <input
                                    type="text"
                                    placeholder="e.g. A minor"
                                    value={stepParams.pitch.key ?? ''}
                                    onChange={(e) =>
                                      patchStepParams('pitch', { key: e.target.value || undefined })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                <label className="flex items-center gap-2 text-gray-600 dark:text-gray-400 sm:col-span-2">
                                  <input
                                    type="checkbox"
                                    checked={stepParams.pitch.chromatic}
                                    onChange={(e) =>
                                      patchStepParams('pitch', { chromatic: e.target.checked })
                                    }
                                  />
                                  Chromatic (snap to nearest semitone instead of the detected key)
                                </label>
                              </>
                            )}

                            {step.key === 'normalize' && (
                              <>
                                <label className="text-gray-600 dark:text-gray-400">
                                  Compression ratio
                                  <input
                                    type="number"
                                    min={1}
                                    step={0.1}
                                    value={stepParams.normalize.compression_ratio}
                                    onChange={(e) =>
                                      patchStepParams('normalize', {
                                        compression_ratio: Number(e.target.value),
                                      })
                                    }
                                    className={inputClass}
                                  />
                                </label>
                                <label className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
                                  <input
                                    type="checkbox"
                                    checked={stepParams.normalize.apply_compression}
                                    onChange={(e) =>
                                      patchStepParams('normalize', {
                                        apply_compression: e.target.checked,
                                      })
                                    }
                                  />
                                  Apply compression
                                </label>
                              </>
                            )}
                          </div>
                        </details>
                      </div>
                    )}
                  </div>
                ))}

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    onClick={() => runClean(true)}
                    disabled={!canRun}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {busy === 'preview' ? 'Previewing…' : 'Preview'}
                  </button>
                  <button
                    onClick={() => runClean(false)}
                    disabled={!canRun}
                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                  >
                    {busy === 'clean' ? 'Cleaning...' : 'Clean to new version'}
                  </button>
                </div>
              </div>
            )}

            {previewCandidatePath && (
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
                    src={`/api/produce/clean/preview?path=${encodeURIComponent(previewCandidatePath)}`}
                    className="h-9 w-full"
                  />
                </div>
                <p className="text-xs text-gray-500 dark:text-gray-400 sm:col-span-2">
                  Preview ready — compare it against the original above. No version was created.
                </p>
              </div>
            )}

            {runResult && !previewCandidatePath && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
                  Result
                </h3>
                {runResult.status === 'error' ? (
                  <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
                    <p className="font-semibold">Failed</p>
                    <p className="mt-1">{runResult.error}</p>
                  </div>
                ) : (
                  <div className="p-4 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 rounded-lg">
                    <p className="font-semibold">
                      Success — {runResult.total_steps} step(s) applied.
                      Saved as a new version below.
                    </p>
                  </div>
                )}
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
        </>
      )}
    </div>
  );
}
