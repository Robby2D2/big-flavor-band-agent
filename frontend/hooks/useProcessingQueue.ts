'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fixCopyFor, manualFixCopy } from '@/components/produce/audio/fixCopy';
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

// Tools whose analyze() returns real measurements (Phase B) — the only ones
// worth calling; the rest always report `recommended: false` today and would
// just be wasted requests (src/production/toolkit.py's base analyze() stub).
// They double as each scope's tool set for the "add a fix" picker: a stem row
// offers the per-stem tools, the full mix the master ones.
const PER_STEM_TOOLS = ['reduce_noise', 'apply_eq', 'remove_hum', 'correct_beats'] as const;
const MASTER_TOOLS = ['trim_silence', 'apply_eq', 'normalize_audio', 'apply_mastering'] as const;

// Plumbing and region bounds are not fixes a producer dials in on a card: the
// first two are filled in by the server, and a card always runs at its row's
// scope (region-scoped manual fixes are deliberately not a thing here).
const NON_TUNABLE_PARAMS = new Set(['file_path', 'output_path', 'start_s', 'end_s']);

/** A tool's declared defaults, as the starting params for a producer-added fix. */
function defaultParamsFor(tool: ToolInfo | undefined): Record<string, any> {
  const out: Record<string, any> = {};
  for (const p of tool?.params ?? []) {
    if (NON_TUNABLE_PARAMS.has(p.name) || p.default == null) continue;
    out[p.name] = p.default;
  }
  return out;
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

/** Run `jobs` a few at a time, keeping only the fixes that came back. */
async function runAnalyzeJobs(
  jobs: Array<() => Promise<FixEntry | null>>
): Promise<FixEntry[]> {
  const results = await mapWithConcurrency(jobs, ANALYZE_CONCURRENCY, (job) => job());
  return results.filter((entry): entry is FixEntry => entry !== null);
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
    async (stemId: number, tool: string): Promise<FixEntry | null> => {
      const res = await fetch(`/api/produce/tools/${tool}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, stem_id: stemId }),
      });
      // Checked before reading the body: one tool failing to analyze — or its
      // response never making it back — shouldn't sink the whole queue.
      if (!res.ok) return null;
      const data = await readJson(res);
      const r = data.result;
      if (!r || !r.recommended) return null;
      const copy = fixCopyFor(tool, r.findings, r.reason);
      return {
        id: `stem:${stemId}:${tool}`,
        scope: 'stem',
        stemId,
        tool,
        title: copy.title,
        body: copy.body,
        confidence: r.confidence ?? null,
        reason: r.reason,
        findings: r.findings || {},
        suggestedParams: r.params || {},
        currentParams: r.params || {},
        enabled: true,
        source: 'analysis',
      };
    },
    [songId]
  );

  const analyzeMasterTool = useCallback(
    async (tool: string): Promise<FixEntry | null> => {
      const res = await fetch(`/api/produce/tools/${tool}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, source_version_id: sourceVersionId }),
      });
      if (!res.ok) return null;
      const data = await readJson(res);
      const r = data.result;
      if (!r || !r.recommended) return null;
      const copy = fixCopyFor(tool, r.findings, r.reason);
      return {
        id: `master:${tool}`,
        scope: 'master',
        stemId: null,
        tool,
        title: copy.title,
        body: copy.body,
        confidence: r.confidence ?? null,
        reason: r.reason,
        findings: r.findings || {},
        suggestedParams: r.params || {},
        currentParams: r.params || {},
        enabled: true,
        source: 'analysis',
      };
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

        const jobs: Array<() => Promise<FixEntry | null>> = [];
        for (const stem of stemSet.stems) {
          for (const tool of PER_STEM_TOOLS) jobs.push(() => analyzeStemTool(stem.id, tool));
        }
        for (const tool of MASTER_TOOLS) jobs.push(() => analyzeMasterTool(tool));

        const results = await runAnalyzeJobs(jobs);
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
        const results = await runAnalyzeJobs(
          isFullMix
            ? MASTER_TOOLS.map((tool) => () => analyzeMasterTool(tool))
            : PER_STEM_TOOLS.map((tool) => () => analyzeStemTool(stemId, tool))
        );
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
    [sourceVersionId, analyzeStemTool, analyzeMasterTool]
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
   * The row's scope decides the set — a stem gets the per-stem tools, the full
   * mix the master ones — narrowed to tools that can actually transform a
   * single file (anything else `apply` would refuse), and minus whatever the
   * row already has a card for, so a tool can never end up on two cards.
   */
  const addableToolsForStem = useCallback(
    (stemId: number): ToolInfo[] => {
      const scoped = stemId === FULL_MIX_STEM_ID ? MASTER_TOOLS : PER_STEM_TOOLS;
      const taken = new Set(
        (stemId === FULL_MIX_STEM_ID
          ? fixes.filter((f) => f.scope === 'master')
          : fixes.filter((f) => f.scope === 'stem' && f.stemId === stemId)
        ).map((f) => f.tool)
      );
      return scoped
        .map((name) => toolsByName[name])
        .filter(
          (tool): tool is ToolInfo =>
            !!tool && tool.applies_to_file && !tool.hidden_from_editor && !taken.has(tool.name)
        );
    },
    [fixes, toolsByName]
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
  const addManualFix = useCallback(
    (stemId: number, tool: string) => {
      const isFullMix = stemId === FULL_MIX_STEM_ID;
      const id = isFullMix ? `master:${tool}` : `stem:${stemId}:${tool}`;
      const params = defaultParamsFor(toolsByName[tool]);
      const copy = manualFixCopy(tool, toolsByName[tool]?.summary);
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
    [toolsByName]
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
  const enabledCount = useMemo(() => fixes.filter((f) => f.enabled).length, [fixes]);

  const buildAcceptPayload = useCallback(
    (preview: boolean) => ({
      song_id: songId,
      source_version_id: sourceVersionId,
      stems: stems.map((s) => ({
        stem_id: s.id,
        fixes: fixesForStem(s.id)
          .filter((f) => f.enabled)
          .map((f) => ({ tool: f.tool, params: f.currentParams })),
      })),
      master_fixes: masterFixes
        .filter((f) => f.enabled)
        .map((f) => ({ tool: f.tool, params: f.currentParams })),
      preview,
    }),
    [songId, sourceVersionId, stems, fixesForStem, masterFixes]
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
        .filter((f) => f.enabled)
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
    [fixesForStem, songId, sourceVersionId]
  );

  // "Hear it" on a single card — renders just that one fix, ignoring every
  // other card's enabled state, so a producer can audition a fix in
  // isolation before deciding whether to keep it.
  const previewSingleFix = useCallback(
    async (fix: FixEntry): Promise<string> => {
      if (fix.scope === 'stem' && fix.stemId != null) {
        const data = await postJson(`/api/produce/stems/${fix.stemId}/preview-chain`, {
          fixes: [{ tool: fix.tool, params: fix.currentParams }],
        });
        return data.candidate_path as string;
      }
      const data = await postJson('/api/produce/accept-fixes', {
        song_id: songId,
        source_version_id: sourceVersionId,
        stems: [],
        master_fixes: [{ tool: fix.tool, params: fix.currentParams }],
        preview: true,
      });
      return data.candidate_path as string;
    },
    [songId, sourceVersionId]
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
    addableToolsForStem,
    addManualFix,
    removeFix,
    updateFixParams,
    resetFixParams,
    acceptAll,
    warmRender,
    previewStemChain,
    previewSingleFix,
    toolParamsByTool,
    ensureToolParams,
  };
}
