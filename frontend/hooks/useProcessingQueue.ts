'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fixCopyFor, fixTitleFor, manualFixCopy } from '@/components/produce/audio/fixCopy';
import { readJson } from '@/lib/apiJson';
import { mapWithConcurrency } from '@/lib/concurrency';

export type Confidence = 'high' | 'worth_a_listen' | null;

export interface StemInstrument {
  label: string;
  score: number;
}

export interface StemInfo {
  id: number;
  /** The Demucs source name — vocals/drums/bass/guitar/piano/other. */
  name: string;
  /** The producer's own label for it, when they've relabelled the stem. */
  displayName: string | null;
  /** What the tagger heard in this stem, strongest first. */
  instruments: StemInstrument[];
  /** The stem came back effectively empty (an instrument the band doesn't play). */
  silent: boolean;
  /** Tagging has run — distinguishes "nothing recognised" from "never tagged". */
  tagged: boolean;
}

/** The label to show for a stem: the producer's, else what Demucs called it. */
export function stemLabel(stem: StemInfo): string {
  return stem.displayName?.trim() || stem.name;
}

export interface ParamMeta {
  name: string;
  type: string;
  default: any;
  min: number | null;
  max: number | null;
  label: string;
  help: string | null;
  /** `apply` refuses without it — `coerce_args` raises rather than defaulting. */
  required: boolean;
  choices: any[] | null;
}

/** One tool as `GET /api/produce/tools` describes it. */
export interface ToolInfo {
  name: string;
  summary: string;
  /** The tool turns one input file into an output — the only kind a fix can be. */
  applies_to_file: boolean;
  /** Whole-song orchestrators, which are pipelines rather than single effects. */
  hidden_from_editor: boolean;
  params: ParamMeta[];
}

export interface FixEntry {
  id: string;
  scope: 'stem' | 'master';
  stemId: number | null;
  tool: string;
  title: string;
  body: string;
  confidence: Confidence;
  reason: string;
  findings: Record<string, any>;
  /** The analysis's own recommended params — the "reset to suggested" target. */
  suggestedParams: Record<string, any>;
  /** Possibly user-adjusted params, sent when this fix is applied. */
  currentParams: Record<string, any>;
  enabled: boolean;
  /** Who put this card in the queue — the analysis, or the producer. */
  source: 'analysis' | 'manual';
}

// Tools whose analyze() returns real measurements — the only ones worth
// *calling during analysis*; the rest always report `recommended: false` and
// would just be wasted requests (src/production/toolkit.py's base analyze()
// stub). This is an analysis concern only: what a producer may add by hand is
// decided by ADDABLE_SCOPE below, since "no detector" is no reason to hide a
// fix somebody can hear.
const PER_STEM_TOOLS = [
  'reduce_noise', 'apply_eq', 'remove_hum', 'correct_beats', 'remove_artifacts',
] as const;
const MASTER_TOOLS = [
  'trim_silence', 'apply_eq', 'normalize_audio', 'apply_mastering', 'remove_artifacts',
] as const;

// Demucs source names whose stem is a single line. pyin tracks one pitch at a
// time, so note detection means nothing anywhere else — and it is the most
// expensive measurement in the pass, so it is worth not spending it.
// `bass` is deliberately out: the detector's floor is C2 (~65 Hz), and a real
// bass stem voiced 2% of the analysis window against a vocal stem's 79%.
const MONOPHONIC_SOURCES = new Set(['vocals']);

// ...and the tagger labels (src/production/instrument_tagging.py's vocabulary)
// that name a single-line instrument, so a fiddle or a harmonica sitting inside
// `other` is measured too.
const MONOPHONIC_INSTRUMENTS = new Set([
  'Vocal', 'Male vocal', 'Female vocal', 'Whistling', 'Humming',
  'Fiddle / violin', 'Cello', 'Harmonica', 'Trumpet', 'Trombone',
  'Saxophone', 'Flute', 'Clarinet', 'French horn',
]);

/**
 * Whether a console row is worth measuring for tuning.
 *
 * The full mix never is — it is polyphonic by definition. The backend refuses
 * a polyphonic source on its own (it can't segment notes out of a chord), so
 * this is about not spending a pyin pass to be told that.
 */
export function isPitchAnalyzable(stem: StemInfo): boolean {
  if (stem.id === FULL_MIX_STEM_ID) return false;
  if (MONOPHONIC_SOURCES.has(stem.name)) return true;
  const strongest = stem.instruments[0];
  return !!strongest && MONOPHONIC_INSTRUMENTS.has(strongest.label);
}

/** The tools to measure on one stem row. */
function analysisToolsFor(stem: StemInfo): string[] {
  return isPitchAnalyzable(stem)
    ? [...PER_STEM_TOOLS, 'correct_pitch']
    : [...PER_STEM_TOOLS];
}

// Where a tool may be added by hand. Every non-hidden single-file tool the
// registry reports is offered on both rows by default — add a tool to the
// backend and it appears here on its own — so this table holds only the
// exceptions, each for a reason that is about the audio, not about tooling.
const ADDABLE_SCOPE: Record<string, 'master' | 'stem'> = {
  // Changes the file's length. Trimming one stem and not its siblings would
  // slide it out of sync with the rest of the set.
  trim_silence: 'master',
  // A mix-bus job by definition: loudness and dynamics judged across the whole
  // song. Run per stem it fights the very balance it is trying to set.
  apply_mastering: 'master',
  normalize_audio: 'master',
};

/** The tools a row may be offered, given the registry and the table above. */
function addableInScope(tools: ToolInfo[], isFullMix: boolean): ToolInfo[] {
  return tools.filter((t) => {
    if (!t.applies_to_file || t.hidden_from_editor) return false;
    const only = ADDABLE_SCOPE[t.name];
    if (!only) return true;
    return only === (isFullMix ? 'master' : 'stem');
  });
}

// Plumbing and region bounds are not fixes a producer dials in on a card: the
// first two are filled in by the server, and a card always runs at its row's
// scope (region-scoped manual fixes are deliberately not a thing here).
const NON_TUNABLE_PARAMS = new Set(['file_path', 'output_path', 'start_s', 'end_s']);

// Starting params for a hand-added card where the tool's own declared defaults
// would do nothing at all. `correct_pitch` defaults to transposing by zero
// semitones with auto-tune off, which is an exact no-op; a producer reaching
// for it wants the notes pulled to pitch, so that is what the card starts as.
const MANUAL_PARAM_OVERRIDES: Record<string, Record<string, any>> = {
  correct_pitch: { auto_tune: true },
};

/**
 * A tool's declared defaults, as the starting params for a producer-added fix.
 *
 * `measured` carries anything the analysis pass already knows about this row —
 * today only the detected tempo, which is what keeps a hand-added `match_tempo`
 * card from arriving in the "needs setup" state. It wins over the declared
 * default, because a number measured from this very song beats a generic one.
 */
function defaultParamsFor(
  tool: ToolInfo | undefined,
  measured: Record<string, any> = {}
): Record<string, any> {
  const out: Record<string, any> = {};
  for (const p of tool?.params ?? []) {
    if (NON_TUNABLE_PARAMS.has(p.name) || p.default == null) continue;
    out[p.name] = p.default;
  }
  return { ...out, ...(tool ? MANUAL_PARAM_OVERRIDES[tool.name] ?? {} : {}), ...measured };
}

/**
 * Required params the card has no value for yet.
 *
 * Most tools have none — every param falls back to its declared default. A few
 * (`match_tempo`'s `target_bpm`) genuinely cannot run without an answer:
 * `coerce_args` raises `ValueError` rather than inventing one, so a card left
 * blank would fail the render rather than quietly do nothing. The card names
 * them and stays out of every chain until they are set.
 */
export function missingRequiredParams(
  tool: ToolInfo | undefined,
  params: Record<string, any>
): ParamMeta[] {
  return (tool?.params ?? []).filter(
    (p) => p.required && !NON_TUNABLE_PARAMS.has(p.name) && params[p.name] == null
  );
}

/**
 * The params the producer moved off the suggested value.
 *
 * Derived rather than tracked, so there is no second copy of the params to keep
 * in sync — it is only needed at the one moment a re-analysis replaces a card
 * the producer had already tuned.
 */
function editedParams(fix: FixEntry): Record<string, any> {
  const out: Record<string, any> = {};
  for (const [key, value] of Object.entries(fix.currentParams)) {
    if (fix.suggestedParams[key] !== value) out[key] = value;
  }
  return out;
}

/**
 * Fold a row's fresh analysis results into what that row already had.
 *
 * Producer-added cards survive a re-analysis — clearing them would make the
 * producer's own judgement the one thing in the queue that a re-measure throws
 * away. When the analysis now recommends a tool they had added, the recommended
 * card wins (it has findings and a confidence the manual one never had) but
 * keeps whatever they had already tuned, so exactly one card per tool remains.
 */
function mergeRowFixes(previous: FixEntry[], results: FixEntry[]): FixEntry[] {
  const recommended = new Set(results.map((f) => f.id));
  const manualById = new Map(
    previous.filter((f) => f.source === 'manual').map((f) => [f.id, f])
  );
  const merged = results.map((fix) => {
    const manual = manualById.get(fix.id);
    if (!manual) return fix;
    return { ...fix, currentParams: { ...fix.currentParams, ...editedParams(manual) } };
  });
  const kept = Array.from(manualById.values()).filter((f) => !recommended.has(f.id));
  return [...merged, ...kept];
}

const IN_FLIGHT = new Set(['queued', 'running']);
const POLL_MS = 4000;
const ANALYZE_CONCURRENCY = 3;

/**
 * The full mix rides in the stem console as a pseudo-stem so the whole song can
 * be played, analyzed and fixed alongside its parts. It is not a real stem row
 * in the database — a negative id can never collide with one — and its "fixes"
 * are the master-scoped fixes, so nothing downstream (accept payloads, apply)
 * has to learn about it.
 */
export const FULL_MIX_STEM_ID = -1;
export const FULL_MIX_STEM_NAME = 'Full mix';

// Instrument tagging runs after a separation job reports complete (so the
// console can show waveforms straight away), which means a freshly separated
// set arrives untagged and the labels land a little later. Poll for them for a
// bounded while rather than making the producer reload the page.
const TAG_POLL_MS = 6000;
const TAG_POLL_ATTEMPTS = 20;

interface StemSetRow {
  id: number;
  status: string;
  source_version_id: number | null;
  stems: StemInfo[];
}

/** Shape one API stem row (snake_case, tags possibly absent) into a StemInfo. */
function toStemInfo(raw: any): StemInfo {
  return {
    id: raw.id,
    name: raw.name,
    displayName: raw.display_name ?? null,
    instruments: raw.instruments ?? [],
    silent: Boolean(raw.silent),
    tagged: Boolean(raw.tagged),
  };
}

async function fetchStemSets(songId: number): Promise<StemSetRow[]> {
  const res = await fetch(`/api/produce/songs/${songId}/stems`);
  const data = await readJson(res);
  if (!res.ok) throw new Error(data.detail || data.error || 'Failed to load stems');
  return (data.stem_sets || []).map((set: any) => ({
    ...set,
    stems: (set.stems || []).map(toStemInfo),
  }));
}

function latestComplete(sets: StemSetRow[]): StemSetRow | undefined {
  return sets
    .filter((s) => s.status === 'complete' && s.stems.length > 0)
    .sort((a, b) => b.id - a.id)[0];
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Fold freshly-fetched tag/label data into the stems already on screen,
 * returning the same array when nothing changed — a poll that finds no new
 * labels shouldn't churn every consumer of `stems`.
 */
function mergeStemTags(current: StemInfo[], incoming: StemInfo[]): StemInfo[] {
  const byId = new Map(incoming.map((s) => [s.id, s]));
  let changed = false;
  const merged = current.map((stem) => {
    const next = byId.get(stem.id);
    if (
      !next ||
      (next.tagged === stem.tagged &&
        next.silent === stem.silent &&
        next.displayName === stem.displayName &&
        next.instruments.length === stem.instruments.length)
    ) {
      return stem;
    }
    changed = true;
    return { ...stem, ...next };
  });
  return changed ? merged : current;
}

/**
 * One tool's verdict on one console row.
 *
 * Kept whole rather than reduced to a fix on the spot, because a *not*
 * recommended result still carries measurements worth having — `correct_beats`
 * reports the song's tempo either way, and that is what a hand-added tempo card
 * starts from.
 */
interface AnalyzeResult {
  recommended?: boolean;
  confidence?: Confidence;
  reason?: string;
  /** Open-shaped by design: every tool measures its own thing. */
  findings?: Record<string, any>;
  params?: Record<string, any>;
}

interface AnalyzeOutcome {
  rowId: number;
  tool: string;
  result: AnalyzeResult;
}

/** Run `jobs` a few at a time, keeping the outcomes that came back. */
async function runAnalyzeJobs(
  jobs: Array<() => Promise<AnalyzeOutcome | null>>
): Promise<AnalyzeOutcome[]> {
  const results = await mapWithConcurrency(jobs, ANALYZE_CONCURRENCY, (job) => job());
  return results.filter((entry): entry is AnalyzeOutcome => entry !== null);
}

/** The recommended outcomes, as queue cards. */
function toFixEntries(outcomes: AnalyzeOutcome[]): FixEntry[] {
  return outcomes
    .filter((o) => o.result?.recommended)
    .map(({ rowId, tool, result }): FixEntry => {
      const isMaster = rowId === FULL_MIX_STEM_ID;
      const copy = fixCopyFor(
        tool, result.findings, result.reason ?? '', isMaster ? 'master' : 'stem'
      );
      return {
        id: isMaster ? `master:${tool}` : `stem:${rowId}:${tool}`,
        scope: isMaster ? 'master' : 'stem',
        stemId: isMaster ? null : rowId,
        tool,
        title: copy.title,
        body: copy.body,
        confidence: result.confidence ?? null,
        reason: result.reason ?? '',
        findings: result.findings || {},
        suggestedParams: result.params || {},
        currentParams: result.params || {},
        enabled: true,
        source: 'analysis',
      };
    });
}

/**
 * The tempo each row measured, recommended or not.
 *
 * `correct_beats` reports `detected_bpm` on every analysis whether or not it
 * thinks the grid is worth correcting, so the song's own tempo is already in
 * hand by the time a producer reaches for the tempo tool.
 */
function measuredTempos(outcomes: AnalyzeOutcome[]): Record<number, number> {
  const out: Record<number, number> = {};
  for (const { rowId, result } of outcomes) {
    const bpm = result?.findings?.detected_bpm;
    if (typeof bpm === 'number' && bpm > 0) out[rowId] = bpm;
  }
  return out;
}

async function postJson(url: string, body: unknown): Promise<any> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await readJson(res);
  if (!res.ok) throw new Error(data.detail || data.error || `${url} failed`);
  return data;
}

/**
 * Owns the review-queue workflow for one song/version: separate into stems if
 * needed, analyze every per-stem and master tool, assemble one FixEntry per
 * detected fix, and turn the enabled subset into a preview or a saved version.
 */
export function useProcessingQueue(songId: number, sourceVersionId: number | null) {
  const [stems, setStems] = useState<StemInfo[]>([]);
  // The full mix is the console's first row, so it is also what's selected
  // before any stem has been picked.
  const [selectedStemId, setSelectedStemId] = useState<number | null>(FULL_MIX_STEM_ID);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  const [analysisNote, setAnalysisNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fixes, setFixes] = useState<FixEntry[]>([]);
  const [toolsByName, setToolsByName] = useState<Record<string, ToolInfo>>({});
  // Which rows have had an analysis pass (so a row that was never measured
  // reads "not analyzed" rather than "clean"), and which are measuring right
  // now — both keyed by stem id, with FULL_MIX_STEM_ID for the whole mix.
  const [analyzedStemIds, setAnalyzedStemIds] = useState<Set<number>>(new Set());

  // Fixes are measurements of one particular version. The moment you work from
  // a different one — including the version a save just produced — they
  // describe audio you are no longer looking at, so they go. Stems are not
  // cleared: they belong to the song, not to a version.
  const previousSourceId = useRef<number | null>(null);
  useEffect(() => {
    const previous = previousSourceId.current;
    previousSourceId.current = sourceVersionId;
    // Not a switch: the first source arriving after mount.
    if (previous === null || previous === sourceVersionId) return;

    setFixes([]);
    setAnalyzed(false);
    setAnalyzedStemIds(new Set());
    setAnalysisNote(null);
  }, [sourceVersionId]);
  const [analyzingStemIds, setAnalyzingStemIds] = useState<Set<number>>(new Set());
  // Tempo as each row measured it. Kept from the analysis pass so a hand-added
  // tempo card can start from the song's own BPM instead of the "needs setup"
  // state — `match_tempo.target_bpm` is the one required param in the registry,
  // and coerce_args raises rather than inventing a value.
  const [detectedBpm, setDetectedBpm] = useState<Record<number, number>>({});
  const [identifyingStemIds, setIdentifyingStemIds] = useState<Set<number>>(new Set());

  // Optimistic preload: a stem set from an earlier session may already sit
  // complete on disk. Show it (waveforms, playback) the moment the tab
  // mounts instead of making the user press "Start analysis" just to see
  // what's already there — fixes still require a real analysis pass, so
  // `analyzed` stays false until that runs.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const sets = await fetchStemSets(songId);
        const complete = latestComplete(sets);
        if (!complete || cancelled) return;
        setStems((prev) => (prev.length > 0 ? prev : complete.stems));
      } catch {
        // Silent — this is just an optimistic preload; Start analysis will
        // surface any real fetch failure.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [songId]);

  // Instrument labels land after separation reports complete, so refresh them
  // in the background while any stem is still untagged. Bounded: tagging that
  // failed leaves a stem untagged forever, and the per-stem Identify button is
  // the retry path for that, not an endless poll.
  const untaggedCount = stems.filter((s) => !s.tagged).length;
  useEffect(() => {
    if (untaggedCount === 0) return;
    let cancelled = false;
    let attempts = 0;
    const timer = setInterval(async () => {
      attempts += 1;
      if (attempts > TAG_POLL_ATTEMPTS) {
        clearInterval(timer);
        return;
      }
      try {
        const complete = latestComplete(await fetchStemSets(songId));
        if (!complete || cancelled) return;
        setStems((prev) => mergeStemTags(prev, complete.stems));
      } catch {
        // Transient — the next tick tries again, and the bound ends it.
      }
    }, TAG_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [songId, untaggedCount]);

  // `forceNew=false` (normal "Start analysis"): never separate over stems that
  // already exist — if the song has a complete stem set, reuse it and go
  // straight to measuring. Demucs costs minutes, so making *new* stems is
  // "Re-separate"'s job alone; separation here is only the first-time path,
  // when the song has no usable stems at all.
  // `forceNew=true` ("Re-separate"): always wait for the *newest* set to
  // finish, even if an older one is already complete — otherwise a forced
  // re-separation would short-circuit straight back to the stale stems.
  const waitForStemSet = useCallback(
    async (forceNew: boolean): Promise<StemSetRow> => {
      let sets = await fetchStemSets(songId);
      const existing = latestComplete(sets);
      if (!forceNew && existing) return existing;

      const alreadyRunning = sets.some((s) => IN_FLIGHT.has(s.status));
      if (!alreadyRunning) {
        await postJson('/api/produce/stems/separate', {
          song_id: songId,
          source_version_id: sourceVersionId,
        });
      }
      setAnalysisNote('Separating into stems — this takes a few minutes…');
      while (true) {
        await sleep(POLL_MS);
        sets = await fetchStemSets(songId);
        const newest = sets.slice().sort((a, b) => b.id - a.id)[0];
        if (newest && newest.status === 'complete' && newest.stems.length > 0) return newest;
        if (newest && newest.status === 'failed') {
          throw new Error((newest as any).error || 'Stem separation failed');
        }
      }
    },
    [songId, sourceVersionId]
  );

  const analyzeStemTool = useCallback(
    async (stemId: number, tool: string): Promise<AnalyzeOutcome | null> => {
      const res = await fetch(`/api/produce/tools/${tool}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, stem_id: stemId }),
      });
      // Checked before reading the body: one tool failing to analyze — or its
      // response never making it back — shouldn't sink the whole queue.
      if (!res.ok) return null;
      const data = await readJson(res);
      if (!data.result) return null;
      return { rowId: stemId, tool, result: data.result };
    },
    [songId]
  );

  const analyzeMasterTool = useCallback(
    async (tool: string): Promise<AnalyzeOutcome | null> => {
      const res = await fetch(`/api/produce/tools/${tool}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, source_version_id: sourceVersionId }),
      });
      if (!res.ok) return null;
      const data = await readJson(res);
      if (!data.result) return null;
      return { rowId: FULL_MIX_STEM_ID, tool, result: data.result };
    },
    [songId, sourceVersionId]
  );

  const runAnalysis = useCallback(
    async (forceNew: boolean) => {
      if (sourceVersionId == null) return;
      setAnalyzing(true);
      setAnalyzed(false);
      setAnalysisNote(null);
      setError(null);
      // Measurements describe audio that is about to be re-measured, so they
      // go; producer-added cards are not measurements and stay put.
      setFixes((prev) => prev.filter((f) => f.source === 'manual'));
      setAnalyzedStemIds(new Set());
      try {
        const stemSet = await waitForStemSet(forceNew);
        setAnalysisNote(null);
        setStems(stemSet.stems);
        setSelectedStemId((prev) =>
          prev === FULL_MIX_STEM_ID || (prev != null && stemSet.stems.some((s) => s.id === prev))
            ? prev
            : FULL_MIX_STEM_ID
        );

        const jobs: Array<() => Promise<AnalyzeOutcome | null>> = [];
        for (const stem of stemSet.stems) {
          for (const tool of analysisToolsFor(stem)) jobs.push(() => analyzeStemTool(stem.id, tool));
        }
        for (const tool of MASTER_TOOLS) jobs.push(() => analyzeMasterTool(tool));

        const outcomes = await runAnalyzeJobs(jobs);
        const results = toFixEntries(outcomes);
        setDetectedBpm(measuredTempos(outcomes));
        // A re-separation mints new stem ids, so a manual card pinned to a stem
        // that no longer exists has nothing left to run against.
        const liveStemIds = new Set(stemSet.stems.map((s) => s.id));
        setFixes((prev) =>
          mergeRowFixes(
            prev.filter((f) => f.scope === 'master' || (f.stemId != null && liveStemIds.has(f.stemId))),
            results
          )
        );
        setAnalyzedStemIds(
          new Set([FULL_MIX_STEM_ID, ...stemSet.stems.map((s) => s.id)])
        );
        setAnalyzed(true);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setAnalyzing(false);
      }
    },
    [sourceVersionId, waitForStemSet, analyzeStemTool, analyzeMasterTool]
  );

  /**
   * Re-measure one console row on its own — a single stem, or the full mix
   * (FULL_MIX_STEM_ID, which runs the master tools). Only that row's fixes are
   * replaced, so a targeted re-analysis never discards the rest of the queue.
   */
  const analyzeStem = useCallback(
    async (stemId: number) => {
      if (sourceVersionId == null) return;
      const isFullMix = stemId === FULL_MIX_STEM_ID;
      setAnalyzingStemIds((prev) => new Set(prev).add(stemId));
      setError(null);
      try {
        const stem = stems.find((s) => s.id === stemId);
        const outcomes = await runAnalyzeJobs(
          isFullMix
            ? MASTER_TOOLS.map((tool) => () => analyzeMasterTool(tool))
            : (stem ? analysisToolsFor(stem) : [...PER_STEM_TOOLS]).map(
                (tool) => () => analyzeStemTool(stemId, tool)
              )
        );
        const results = toFixEntries(outcomes);
        setDetectedBpm((prev) => ({ ...prev, ...measuredTempos(outcomes) }));
        setFixes((prev) => {
          const onThisRow = (f: FixEntry) =>
            isFullMix ? f.scope === 'master' : f.scope === 'stem' && f.stemId === stemId;
          return [
            ...prev.filter((f) => !onThisRow(f)),
            ...mergeRowFixes(prev.filter(onThisRow), results),
          ];
        });
        setAnalyzedStemIds((prev) => new Set(prev).add(stemId));
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setAnalyzingStemIds((prev) => {
          const next = new Set(prev);
          next.delete(stemId);
          return next;
        });
      }
    },
    [sourceVersionId, stems, analyzeStemTool, analyzeMasterTool]
  );

  const startAnalysis = useCallback(() => runAnalysis(false), [runAnalysis]);
  // "Re-separate": always runs a fresh Demucs job before re-analyzing, unlike
  // Start analysis which reuses an already-complete stem set.
  const reseparateAndAnalyze = useCallback(() => runAnalysis(true), [runAnalysis]);

  /**
   * Relabel a stem — Demucs can only call a banjo "other", so the producer
   * gets the last word on what a stem is. An empty name clears the override
   * back to the Demucs source name.
   */
  const renameStem = useCallback(async (stemId: number, displayName: string) => {
    const trimmed = displayName.trim();
    // Optimistic: renaming is a label edit, and bouncing back on a failed
    // request is less jarring than a field that lags every keystroke.
    setStems((prev) =>
      prev.map((s) => (s.id === stemId ? { ...s, displayName: trimmed || null } : s))
    );
    try {
      const res = await fetch(`/api/produce/stems/${stemId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ display_name: trimmed }),
      });
      const data = await readJson(res);
      if (!res.ok) throw new Error(data.detail || data.error || 'Failed to rename stem');
      setStems((prev) => prev.map((s) => (s.id === stemId ? toStemInfo(data.stem) : s)));
    } catch (err) {
      setError((err as Error).message);
      const complete = latestComplete(await fetchStemSets(songId).catch(() => []));
      if (complete) setStems((prev) => mergeStemTags(prev, complete.stems));
    }
  }, [songId]);

  /** Re-run instrument detection on one stem (the retry path for a failed tag). */
  const identifyStem = useCallback(async (stemId: number) => {
    setIdentifyingStemIds((prev) => new Set(prev).add(stemId));
    try {
      const data = await postJson(`/api/produce/stems/${stemId}/identify`, {});
      setStems((prev) => prev.map((s) => (s.id === stemId ? toStemInfo(data.stem) : s)));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIdentifyingStemIds((prev) => {
        const next = new Set(prev);
        next.delete(stemId);
        return next;
      });
    }
  }, []);

  const toggleFix = useCallback((id: string) => {
    setFixes((prev) => prev.map((f) => (f.id === id ? { ...f, enabled: !f.enabled } : f)));
  }, []);

  /**
   * The tools a producer can still add to one console row.
   *
   * Taken from the registry rather than a hand-kept list: every tool that can
   * transform a single file and isn't a pipeline is offered, minus the ones
   * `ADDABLE_SCOPE` pins to the other scope, minus whatever the row already has
   * a card for — so a tool can never end up on two cards, and a tool added to
   * the backend shows up here without a frontend change. Tools with no
   * `analyze()` of their own (correct_pitch, remove_artifacts, match_tempo) are
   * *only* ever reachable this way; nothing can recommend them.
   */
  const addableToolsForStem = useCallback(
    (stemId: number): ToolInfo[] => {
      const isFullMix = stemId === FULL_MIX_STEM_ID;
      const taken = new Set(
        (isFullMix
          ? fixes.filter((f) => f.scope === 'master')
          : fixes.filter((f) => f.scope === 'stem' && f.stemId === stemId)
        ).map((f) => f.tool)
      );
      return addableInScope(Object.values(toolsByName), isFullMix)
        .filter((tool) => !taken.has(tool.name))
        .sort((a, b) => fixTitleFor(a.name, a.summary).localeCompare(fixTitleFor(b.name, b.summary)));
    },
    [fixes, toolsByName]
  );

  /**
   * Cards that cannot run yet because a required param has no value.
   *
   * They stay in the queue and on screen — removing them would hide the one
   * thing the producer needs to act on — but they are kept out of every chain
   * that gets rendered, so a blank `target_bpm` can never turn into a failed
   * render or a save that silently dropped a fix.
   */
  const incompleteFixIds = useMemo(
    () =>
      new Set(
        fixes
          .filter((f) => missingRequiredParams(toolsByName[f.tool], f.currentParams).length > 0)
          .map((f) => f.id)
      ),
    [fixes, toolsByName]
  );

  /** What a card still needs before it can be enabled — empty when it's ready. */
  const missingParamsFor = useCallback(
    (fix: FixEntry) => missingRequiredParams(toolsByName[fix.tool], fix.currentParams),
    [toolsByName]
  );

  /** Enabled *and* runnable — the test every chain-building path applies. */
  const isRunnable = useCallback(
    (f: FixEntry) => f.enabled && !incompleteFixIds.has(f.id),
    [incompleteFixIds]
  );

  /**
   * Put a fix in the queue the analysis never recommended.
   *
   * It starts from the tool's own declared defaults — there are no measured
   * numbers to pre-fill, which is exactly why the Adjust drawer is where the
   * amount gets set. Everything downstream (Hear it, the accept payload, the
   * render fingerprint) reads `tool` + `currentParams` and never asks where a
   * card came from, so it behaves like any other from here on.
   */
  /**
   * The tempo to start a hand-added `match_tempo` card from.
   *
   * The row's own measurement first, then any other row's — the stems are all
   * the same performance, so the drums' BPM is the song's BPM, which is what
   * lets the full-mix row (whose analysis list has no beat detector) offer a
   * runnable card too.
   */
  const tempoSeedFor = useCallback(
    (rowId: number): number | undefined => {
      const own = detectedBpm[rowId];
      if (own) return own;
      const any = Object.values(detectedBpm).filter((bpm) => bpm > 0);
      return any.length ? any[0] : undefined;
    },
    [detectedBpm]
  );

  const addManualFix = useCallback(
    (stemId: number, tool: string) => {
      const isFullMix = stemId === FULL_MIX_STEM_ID;
      const id = isFullMix ? `master:${tool}` : `stem:${stemId}:${tool}`;
      const bpm = tool === 'match_tempo' ? tempoSeedFor(stemId) : undefined;
      const params = defaultParamsFor(
        toolsByName[tool],
        bpm ? { target_bpm: Math.round(bpm * 10) / 10 } : {}
      );
      const copy = manualFixCopy(
        tool, toolsByName[tool]?.summary, isFullMix ? 'master' : 'stem', params
      );
      setFixes((prev) =>
        prev.some((f) => f.id === id)
          ? prev
          : [
              ...prev,
              {
                id,
                scope: isFullMix ? 'master' : 'stem',
                stemId: isFullMix ? null : stemId,
                tool,
                title: copy.title,
                body: copy.body,
                confidence: null,
                reason: '',
                findings: {},
                suggestedParams: params,
                currentParams: { ...params },
                enabled: true,
                source: 'manual',
              },
            ]
      );
    },
    [toolsByName, tempoSeedFor]
  );

  /**
   * Drop a producer-added card. Only those: a recommended fix is a measurement
   * of the audio, and turning it off is what "I don't want this one" means.
   */
  const removeFix = useCallback((id: string) => {
    setFixes((prev) => prev.filter((f) => !(f.id === id && f.source === 'manual')));
  }, []);

  const updateFixParams = useCallback((id: string, patch: Record<string, any>) => {
    setFixes((prev) =>
      prev.map((f) => (f.id === id ? { ...f, currentParams: { ...f.currentParams, ...patch } } : f))
    );
  }, []);

  const resetFixParams = useCallback((id: string) => {
    setFixes((prev) =>
      prev.map((f) => (f.id === id ? { ...f, currentParams: { ...f.suggestedParams } } : f))
    );
  }, []);

  // The full-mix row's "stem fixes" are the master-scoped ones — that's what
  // makes it behave like any other row in the console and the fix queue.
  const fixesForStem = useCallback(
    (stemId: number) =>
      stemId === FULL_MIX_STEM_ID
        ? fixes.filter((f) => f.scope === 'master')
        : fixes.filter((f) => f.scope === 'stem' && f.stemId === stemId),
    [fixes]
  );

  const masterFixes = useMemo(() => fixes.filter((f) => f.scope === 'master'), [fixes]);

  /** The console's rows: the whole song first, then each separated stem. */
  const consoleStems = useMemo<StemInfo[]>(
    () => [
      {
        id: FULL_MIX_STEM_ID,
        name: FULL_MIX_STEM_NAME,
        displayName: null,
        // The whole song is every instrument by definition — tagging it would
        // just list the union of the stems, so it's never tagged or relabelled.
        instruments: [],
        silent: false,
        tagged: true,
      },
      ...stems,
    ],
    [stems]
  );
  // Counts what would actually be rendered, so the button never promises a fix
  // that is sitting incomplete.
  const enabledCount = useMemo(() => fixes.filter(isRunnable).length, [fixes, isRunnable]);

  const buildAcceptPayload = useCallback(
    (preview: boolean) => ({
      song_id: songId,
      source_version_id: sourceVersionId,
      stems: stems.map((s) => ({
        stem_id: s.id,
        fixes: fixesForStem(s.id)
          .filter(isRunnable)
          .map((f) => ({ tool: f.tool, params: f.currentParams })),
      })),
      master_fixes: masterFixes
        .filter(isRunnable)
        .map((f) => ({ tool: f.tool, params: f.currentParams })),
      preview,
    }),
    [songId, sourceVersionId, stems, fixesForStem, masterFixes, isRunnable]
  );

  /**
   * Hand a whole-queue render to the background runner.
   *
   * Returns as soon as the server has taken the job — it may already be
   * `complete` when this exact fix set was rendered earlier (Start analysis
   * renders the detected queue, so the usual case is a hit), otherwise it is
   * `running` and the page follows it via useAcceptJob.
   */
  const startAcceptRender = useCallback(
    async (preview: boolean) =>
      postJson('/api/produce/accept-fixes/start', buildAcceptPayload(preview)),
    [buildAcceptPayload]
  );

  /** Poll a started render to the end — only for previews, which need the file. */
  const waitForAcceptRender = useCallback(async (): Promise<any> => {
    for (;;) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const res = await fetch(`/api/produce/songs/${songId}/accept-fixes/status`);
      if (!res.ok) throw new Error('Lost track of the render');
      const job = await readJson(res);
      if (job.status === 'complete') return job;
      if (job.status === 'failed') throw new Error(job.error || 'The render failed');
      if (job.status === 'idle') throw new Error('The render is no longer running');
    }
  }, [songId]);

  /** "Accept all & save version" — starts the save and returns; the page watches. */
  const acceptAll = useCallback(
    async (preview: boolean) => {
      const job = await startAcceptRender(preview);
      if (job.status === 'complete' || !preview) return job;
      // A preview has to wait: the caller needs a file to play.
      return waitForAcceptRender();
    },
    [startAcceptRender, waitForAcceptRender]
  );

  /**
   * Render the detected queue right after analysing it.
   *
   * Analysis only *measures* — every fix was still unrendered when the producer
   * pressed a button, which is why saving took minutes. Since the reason to
   * analyse is almost always to hear or keep the result, the render now starts
   * as soon as the findings are in, and Preview/Save land on a finished file.
   */
  const warmRender = useCallback(async () => {
    try {
      await startAcceptRender(true);
    } catch {
      // Best-effort: a failed warm-up just means Preview/Save render on demand.
    }
  }, [startAcceptRender]);

  const previewStemChain = useCallback(
    async (stemId: number): Promise<string> => {
      const chain = fixesForStem(stemId)
        .filter(isRunnable)
        .map((f) => ({ tool: f.tool, params: f.currentParams }));
      // The full mix has no stem file to run a chain over — its chain is the
      // master fixes rendered against the source version.
      if (stemId === FULL_MIX_STEM_ID) {
        const data = await postJson('/api/produce/accept-fixes', {
          song_id: songId,
          source_version_id: sourceVersionId,
          stems: [],
          master_fixes: chain,
          preview: true,
        });
        return data.candidate_path as string;
      }
      const data = await postJson(`/api/produce/stems/${stemId}/preview-chain`, { fixes: chain });
      return data.candidate_path as string;
    },
    [fixesForStem, songId, sourceVersionId, isRunnable]
  );

  const ensureToolParams = useCallback(async () => {
    if (Object.keys(toolsByName).length) return;
    try {
      const res = await fetch('/api/produce/tools');
      if (!res.ok) return;
      const data = await readJson(res);
      const map: Record<string, ToolInfo> = {};
      for (const t of data.tools || []) {
        map[t.name] = {
          name: t.name,
          summary: t.summary || t.name,
          applies_to_file: Boolean(t.applies_to_file),
          hidden_from_editor: Boolean(t.hidden_from_editor),
          params: t.params || [],
        };
      }
      setToolsByName(map);
    } catch {
      // Advanced-drawer metadata is a nice-to-have; a fetch failure just
      // means the drawer falls back to plain number inputs.
    }
  }, [toolsByName]);

  const toolParamsByTool = useMemo(() => {
    const map: Record<string, ParamMeta[]> = {};
    for (const [name, tool] of Object.entries(toolsByName)) map[name] = tool.params;
    return map;
  }, [toolsByName]);

  return {
    stems,
    consoleStems,
    selectedStemId,
    setSelectedStemId,
    analyzing,
    analyzed,
    analyzedStemIds,
    analyzingStemIds,
    identifyingStemIds,
    analysisNote,
    error,
    fixes,
    fixesForStem,
    masterFixes,
    enabledCount,
    startAnalysis,
    reseparateAndAnalyze,
    analyzeStem,
    renameStem,
    identifyStem,
    toggleFix,
    missingParamsFor,
    incompleteFixIds,
    addableToolsForStem,
    addManualFix,
    removeFix,
    updateFixParams,
    resetFixParams,
    acceptAll,
    warmRender,
    previewStemChain,
    toolParamsByTool,
    ensureToolParams,
  };
}
