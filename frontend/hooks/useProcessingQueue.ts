'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { fixCopyFor } from '@/components/produce/audio/fixCopy';

export type Confidence = 'high' | 'worth_a_listen' | null;

export interface StemInfo {
  id: number;
  name: string;
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
}

// Tools whose analyze() returns real measurements (Phase B) — the only ones
// worth calling; the rest always report `recommended: false` today and would
// just be wasted requests (src/production/toolkit.py's base analyze() stub).
const PER_STEM_TOOLS = ['reduce_noise', 'apply_eq', 'remove_hum', 'correct_beats'] as const;
const MASTER_TOOLS = ['trim_silence', 'apply_eq', 'normalize_audio', 'apply_mastering'] as const;

const IN_FLIGHT = new Set(['queued', 'running']);
const POLL_MS = 4000;
const ANALYZE_CONCURRENCY = 3;

interface StemSetRow {
  id: number;
  status: string;
  source_version_id: number | null;
  stems: StemInfo[];
}

async function fetchStemSets(songId: number): Promise<StemSetRow[]> {
  const res = await fetch(`/api/produce/songs/${songId}/stems`);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || data.error || 'Failed to load stems');
  return data.stem_sets || [];
}

function latestComplete(sets: StemSetRow[]): StemSetRow | undefined {
  return sets
    .filter((s) => s.status === 'complete' && s.stems.length > 0)
    .sort((a, b) => b.id - a.id)[0];
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function postJson(url: string, body: unknown): Promise<any> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
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
  const [selectedStemId, setSelectedStemId] = useState<number | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);
  const [analysisNote, setAnalysisNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fixes, setFixes] = useState<FixEntry[]>([]);
  const [toolParamsByTool, setToolParamsByTool] = useState<Record<string, any[]>>({});

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
        setSelectedStemId((prev) => (prev != null ? prev : complete.stems[0]?.id ?? null));
      } catch {
        // Silent — this is just an optimistic preload; Start analysis will
        // surface any real fetch failure.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [songId]);

  // `forceNew=false` (normal "Start analysis"): reuse an existing complete
  // stem set if one exists, else kick off separation and wait for it.
  // `forceNew=true` ("Re-separate"): always wait for the *newest* set to
  // finish, even if an older one is already complete — otherwise a forced
  // re-separation would short-circuit straight back to the stale stems.
  const waitForStemSet = useCallback(
    async (forceNew: boolean): Promise<StemSetRow> => {
      let sets = await fetchStemSets(songId);
      if (!forceNew) {
        const complete = latestComplete(sets);
        if (complete) return complete;
      }

      const alreadyRunning = sets.some((s) => IN_FLIGHT.has(s.status));
      if (!alreadyRunning) {
        await postJson('/api/produce/stems/separate', {
          song_id: songId,
          source_version_id: sourceVersionId,
        });
      }
      setAnalysisNote('Separating into stems — this takes a few minutes…');
      // eslint-disable-next-line no-constant-condition
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
    async (stem: StemInfo, tool: string): Promise<FixEntry | null> => {
      const res = await fetch(`/api/produce/tools/${tool}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ song_id: songId, stem_id: stem.id }),
      });
      const data = await res.json();
      if (!res.ok) return null; // one tool failing to analyze shouldn't sink the whole queue
      const r = data.result;
      if (!r || !r.recommended) return null;
      const copy = fixCopyFor(tool, r.findings, r.reason);
      return {
        id: `stem:${stem.id}:${tool}`,
        scope: 'stem',
        stemId: stem.id,
        tool,
        title: copy.title,
        body: copy.body,
        confidence: r.confidence ?? null,
        reason: r.reason,
        findings: r.findings || {},
        suggestedParams: r.params || {},
        currentParams: r.params || {},
        enabled: true,
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
      const data = await res.json();
      if (!res.ok) return null;
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
      setFixes([]);
      try {
        const stemSet = await waitForStemSet(forceNew);
        setAnalysisNote(null);
        setStems(stemSet.stems);
        setSelectedStemId((prev) =>
          prev != null && stemSet.stems.some((s) => s.id === prev) ? prev : stemSet.stems[0]?.id ?? null
        );

        const jobs: Array<() => Promise<FixEntry | null>> = [];
        for (const stem of stemSet.stems) {
          for (const tool of PER_STEM_TOOLS) jobs.push(() => analyzeStemTool(stem, tool));
        }
        for (const tool of MASTER_TOOLS) jobs.push(() => analyzeMasterTool(tool));

        const results: FixEntry[] = [];
        let cursor = 0;
        const worker = async () => {
          while (cursor < jobs.length) {
            const job = jobs[cursor++];
            const entry = await job();
            if (entry) results.push(entry);
          }
        };
        await Promise.all(
          Array.from({ length: Math.min(ANALYZE_CONCURRENCY, jobs.length) }, worker)
        );

        setFixes(results);
        setAnalyzed(true);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setAnalyzing(false);
      }
    },
    [sourceVersionId, waitForStemSet, analyzeStemTool, analyzeMasterTool]
  );

  const startAnalysis = useCallback(() => runAnalysis(false), [runAnalysis]);
  // "Re-separate": always runs a fresh Demucs job before re-analyzing, unlike
  // Start analysis which reuses an already-complete stem set.
  const reseparateAndAnalyze = useCallback(() => runAnalysis(true), [runAnalysis]);

  const toggleFix = useCallback((id: string) => {
    setFixes((prev) => prev.map((f) => (f.id === id ? { ...f, enabled: !f.enabled } : f)));
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

  const fixesForStem = useCallback(
    (stemId: number) => fixes.filter((f) => f.scope === 'stem' && f.stemId === stemId),
    [fixes]
  );

  const masterFixes = useMemo(() => fixes.filter((f) => f.scope === 'master'), [fixes]);
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

  const acceptAll = useCallback(
    async (preview: boolean) => postJson('/api/produce/accept-fixes', buildAcceptPayload(preview)),
    [buildAcceptPayload]
  );

  const previewStemChain = useCallback(
    async (stemId: number): Promise<string> => {
      const chain = fixesForStem(stemId)
        .filter((f) => f.enabled)
        .map((f) => ({ tool: f.tool, params: f.currentParams }));
      const data = await postJson(`/api/produce/stems/${stemId}/preview-chain`, { fixes: chain });
      return data.candidate_path as string;
    },
    [fixesForStem]
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
    if (Object.keys(toolParamsByTool).length) return;
    try {
      const res = await fetch('/api/produce/tools');
      const data = await res.json();
      if (!res.ok) return;
      const map: Record<string, any[]> = {};
      for (const t of data.tools || []) map[t.name] = t.params || [];
      setToolParamsByTool(map);
    } catch {
      // Advanced-drawer metadata is a nice-to-have; a fetch failure just
      // means the drawer falls back to plain number inputs.
    }
  }, [toolParamsByTool]);

  return {
    stems,
    selectedStemId,
    setSelectedStemId,
    analyzing,
    analyzed,
    analysisNote,
    error,
    fixes,
    fixesForStem,
    masterFixes,
    enabledCount,
    startAnalysis,
    reseparateAndAnalyze,
    toggleFix,
    updateFixParams,
    resetFixParams,
    acceptAll,
    previewStemChain,
    previewSingleFix,
    toolParamsByTool,
    ensureToolParams,
  };
}
