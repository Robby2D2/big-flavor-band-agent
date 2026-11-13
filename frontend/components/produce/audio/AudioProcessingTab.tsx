'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  useProcessingQueue,
  FixEntry,
  FULL_MIX_STEM_ID,
  StemInfo,
  stemLabel,
} from '@/hooks/useProcessingQueue';
import type { AcceptJob } from '@/hooks/useAcceptJob';
import { buildTasks, TaskId } from '@/lib/processingTasks';
import { decodeAudio, fetchPeaks, WaveformPeaks } from '../audioEngine';
import { mapWithConcurrency } from '@/lib/concurrency';
import { addTake, chainSignature, ChainStep, neighbourChains, takeKey } from '@/lib/fixTakes';
import type { StemPlaybackControl } from './useStemPlayback';
import { useStemPlayback } from './useStemPlayback';
import VersionDetails, { VersionDetail } from './VersionDetails';
import StemConsole from './StemConsole';
import FixQueue from './FixQueue';
import AdvancedDrawer from './AdvancedDrawer';
import ResultSidebar from './ResultSidebar';
import LyricsCard from './LyricsCard';
import TaskPanel from './TaskPanel';
import TransportBar from './TransportBar';

/**
 * How many stems to render through their fix chains at once.
 *
 * The rendering is CPU-bound on the server, so all six stems at once doesn't
 * finish the batch any sooner — it just stretches every one of those requests
 * to the length of the whole batch, which is how they end up past the reverse
 * proxy's read timeout and come back as an error page instead of audio.
 */
const RENDER_CONCURRENCY = 2;

/**
 * How many rendered takes to keep decoded across all rows. A decoded stem is
 * tens of MB, so this is a memory budget: enough for every row's current take
 * plus the selected row's one-toggle-away takes, which is what makes ON/OFF
 * instant. Takes that are playing are never evicted.
 */
const MAX_TAKES = 10;

/** Settle time before rendering the selected row's neighbouring takes, so a slider drag doesn't start one per step. */
const NEIGHBOUR_DELAY_MS = 800;

interface AudioProcessingTabProps {
  songId: number;
  versions: VersionDetail[];
  /** Which version is selected, owned by the page so the list can drive it. */
  sourceVersionId: number | null;
  onApplied: () => void;
  /** Tell the page a background render just started, so it begins polling. */
  onRenderStarted: () => void;
  /** The song's whole-queue render, which the page polls (useAcceptJob). */
  renderJob: AcceptJob;
  /** Stop that render, or only the save riding on it (PROD-19). */
  onCancelRender: (saveOnly: boolean) => Promise<void>;
  /** Forget a finished render, clearing its task from the panel. */
  onDismissRender: () => void;
  /** Acting on the selected version — the page owns these mutations. */
  versionActions: {
    busyId: number | null;
    onSetDefault: (versionId: number) => void;
    onRename: (versionId: number, name: string) => void;
    onDelete: (versionId: number, name: string) => void;
  };
}

/**
 * The Audio processing panel: pick a version, run one analysis pass,
 * then review a queue of detected fixes (one card per fix, pre-filled with
 * the tool's own real measured numbers) grouped by stem, and accept the ones
 * you want as a single new version. Replaces the old per-tool checkbox list
 * (MultitrackEditor) — the interaction model is different enough that a new
 * component tree was cleaner than patching the old one.
 */
export default function AudioProcessingTab({
  songId,
  versions,
  sourceVersionId,
  onApplied,
  onRenderStarted,
  renderJob,
  onCancelRender,
  onDismissRender,
  versionActions,
}: AudioProcessingTabProps) {
  const selectedVersion = versions.find((v) => v.id === sourceVersionId) ?? null;
  const renderInProgress = renderJob.status === 'running';

  const queue = useProcessingQueue(songId, sourceVersionId);

  // The server starts rendering the moment a pass's findings land, so play,
  // Preview and Save meet finished audio. All the page does is start following
  // that render (`analyzed` is reset to false at the start of each pass, and a
  // cancelled pass never sets it).
  const { analyzed, warmRender } = queue;
  useEffect(() => {
    if (analyzed) onRenderStarted();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [analyzed]);

  const [peaks, setPeaks] = useState<Record<number, WaveformPeaks>>({});
  const [peaksLoadingIds, setPeaksLoadingIds] = useState<Set<number>>(new Set());
  const [peaksError, setPeaksError] = useState<string | null>(null);
  const [buffers, setBuffers] = useState<Record<number, AudioBuffer>>({});
  const [controls, setControls] = useState<Record<number, StemPlaybackControl>>({});
  const [drawerFix, setDrawerFix] = useState<FixEntry | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);
  const [taskError, setTaskError] = useState<string | null>(null);

  // How far each row's playback audio has downloaded, for the transport's
  // "Loading audio" line. Dropped once the row decodes.
  const [audioProgress, setAudioProgress] = useState<
    Record<number, { loaded: number; total: number | null }>
  >({});

  const fetchedPeakUrls = useRef<Map<number, string>>(new Map());
  const decodedUrls = useRef<Map<number, string>>(new Map());

  // Confirmed-silent stems never get a row in the console (see StemConsole),
  // so there is nothing to draw or play for them.
  const audibleStems = queue.stems.filter((s) => !s.silent);
  const stemIdsKey = audibleStems.map((s) => s.id).join(',');

  const targets = useMemo(
    () =>
      sourceVersionId == null
        ? []
        : [
            {
              id: FULL_MIX_STEM_ID,
              peaks: `/api/produce/versions/${sourceVersionId}/peaks`,
              audio: `/api/produce/versions/${sourceVersionId}/preview`,
            },
            ...audibleStems.map((s) => ({
              id: s.id,
              peaks: `/api/produce/stems/${s.id}/peaks`,
              audio: `/api/produce/stems/${s.id}/preview`,
            })),
          ],
    // `stemIdsKey` stands in for queue.stems: a fresh array arrives on every
    // analysis pass, but only a different set of stem ids should refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sourceVersionId, stemIdsKey]
  );

  // Waveforms: a few KB per row, so this is what the console actually waits on.
  // Everything visible — the transport, the sparklines, the detail waveform,
  // and the timeline itself — comes from here rather than from decoded audio.
  useEffect(() => {
    if (targets.length === 0) return;
    const targetIds = new Set(targets.map((t) => t.id));

    // Drop anything that is no longer a console row (a re-separation replacing
    // the stem set), and keep what is still current — including the user's
    // mute/solo/gain for rows that survived.
    for (const id of Array.from(fetchedPeakUrls.current.keys())) {
      if (!targetIds.has(id)) fetchedPeakUrls.current.delete(id);
    }
    for (const id of Array.from(decodedUrls.current.keys())) {
      if (!targetIds.has(id)) decodedUrls.current.delete(id);
    }
    const keepCurrent = <T,>(prev: Record<number, T>) =>
      Object.fromEntries(Object.entries(prev).filter(([id]) => targetIds.has(Number(id))));
    // Pruned here, beside the ref caches above, so state and caches always
    // agree on which rows exist; one extra render per stem-set change is cheap.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setPeaks(keepCurrent);
    setBuffers(keepCurrent);
    setControls((prev) =>
      Object.fromEntries(
        targets.map((t) => [
          t.id,
          // The stems already add up to the full mix, so the mix channel starts
          // muted — un-mute or solo it to hear the mix itself.
          prev[t.id] ?? { gain: 1, mute: t.id === FULL_MIX_STEM_ID, solo: false },
        ])
      )
    );

    const pending = targets.filter((t) => fetchedPeakUrls.current.get(t.id) !== t.peaks);
    if (pending.length === 0) return;

    let cancelled = false;
    setPeaksError(null);
    setPeaksLoadingIds(new Set(pending.map((t) => t.id)));
    void Promise.all(
      pending.map(async (t) => {
        try {
          const loaded = await fetchPeaks(t.peaks);
          if (cancelled) return;
          fetchedPeakUrls.current.set(t.id, t.peaks);
          setPeaks((prev) => ({ ...prev, [t.id]: loaded }));
        } catch (err) {
          if (!cancelled) setPeaksError((err as Error).message);
        } finally {
          if (!cancelled) {
            setPeaksLoadingIds((prev) => {
              const next = new Set(prev);
              next.delete(t.id);
              return next;
            });
          }
        }
      })
    );
    return () => {
      cancelled = true;
    };
  }, [targets]);

  // The mix channel starts muted and the stems already sum to it, so its audio
  // is only worth fetching once the producer un-mutes or solos that row.
  // Deliberately a boolean rather than reading `controls` inside the effect
  // below: `controls` is rebuilt as a fresh object on every stem-set change, so
  // depending on it would restart the fan-out for an unrelated gain tweak.
  const fullMixControl = controls[FULL_MIX_STEM_ID];
  const fullMixAudible = !!fullMixControl && (!fullMixControl.mute || fullMixControl.solo);

  // Playback audio, prefetched behind the waveforms. These are compressed
  // copies (~15x smaller than the source WAVs), decoded up front so pressing
  // play is instant — but nothing on screen waits for them.
  useEffect(() => {
    const wanted = targets.filter((t) => t.id !== FULL_MIX_STEM_ID || fullMixAudible);
    const pending = wanted.filter((t) => decodedUrls.current.get(t.id) !== t.audio);
    if (pending.length === 0) return;

    let cancelled = false;
    void Promise.all(
      pending.map(async (t) => {
        // Claim it up front so a re-render mid-decode doesn't start a second
        // fetch — but the claim has to be released on every path that doesn't
        // produce a buffer, or a cancelled run leaves the row permanently
        // "already fetched" and playback never becomes ready.
        decodedUrls.current.set(t.id, t.audio);
        // A stem arrives in hundreds of chunks; re-render per percent, not per chunk.
        let shown = -1;
        const onProgress = (loaded: number, total: number | null) => {
          const step = total ? Math.floor((loaded / total) * 100) : Math.floor(loaded / 1_000_000);
          if (cancelled || step === shown) return;
          shown = step;
          setAudioProgress((prev) => ({ ...prev, [t.id]: { loaded, total } }));
        };
        const forget = () =>
          setAudioProgress((prev) => {
            const next = { ...prev };
            delete next[t.id];
            return next;
          });
        try {
          const buffer = await decodeAudio(t.audio, onProgress);
          if (cancelled) {
            decodedUrls.current.delete(t.id);
            forget();
            return;
          }
          setBuffers((prev) => ({ ...prev, [t.id]: buffer }));
          forget();
        } catch (err) {
          decodedUrls.current.delete(t.id);
          forget();
          if (!cancelled) setPlaybackError((err as Error).message);
        }
      })
    );
    return () => {
      cancelled = true;
    };
  }, [targets, fullMixAudible]);

  useEffect(() => {
    queue.ensureToolParams();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.analyzed]);

  // The timeline comes from the waveform envelopes, so the transport is scaled
  // correctly before any audio has finished decoding.
  const serverMaxDuration = useMemo(
    () => Object.values(peaks).reduce((m, p) => Math.max(m, p.duration), 0),
    [peaks]
  );
  // What the transport plays for each row: its rendered fix chain when that
  // render matches the row's enabled fixes, otherwise the raw audio. The
  // transport is the only player on the page, so "with fixes" is what you
  // simply hear once it is ready — and the bar says when it is not.
  // Several takes per row, keyed by row + chain (`takeKey`), so toggling back
  // to a state already heard — or one rendered ahead — swaps in at once.
  const [takes, setTakes] = useState<Map<string, AudioBuffer>>(new Map());
  const takesRef = useRef(takes);
  useLayoutEffect(() => {
    takesRef.current = takes;
  }, [takes]);
  // Renders on their way, shared so a toggle that lands on a take already
  // being rendered ahead waits for it instead of rendering it twice.
  const pendingTakesRef = useRef<Map<string, Promise<AudioBuffer>>>(new Map());
  // The full-mix row has the same id on every version, so its takes would
  // otherwise outlive the version they were rendered from. Dropped during the
  // render that sees the new version (React's "adjust state on a prop change"),
  // so no frame ever pairs the new version with the old takes.
  // The transport's Fixes switch: every row plays its raw audio while set. A
  // listening switch only — which fixes are on, and so what a save contains,
  // is untouched. The raw audio is always decoded, so the swap is immediate.
  const [bypassFixes, setBypassFixes] = useState(false);
  const [takesVersionId, setTakesVersionId] = useState(sourceVersionId);
  if (takesVersionId !== sourceVersionId) {
    setTakesVersionId(sourceVersionId);
    setTakes(new Map());
    setBypassFixes(false);
  }
  useEffect(() => {
    pendingTakesRef.current.clear();
  }, [sourceVersionId]);
  // Rows rendering in the background so they can play with their fixes, and
  // how far that has got — counted for the task panel.
  const [playbackRendering, setPlaybackRendering] = useState<number[]>([]);
  const [playbackLoad, setPlaybackLoad] = useState<{
    done: number;
    total: number;
    afterRender: boolean;
  } | null>(null);
  const inFlightRef = useRef<Set<number>>(new Set());
  // Bumped by "Play without" to drop the renders in flight.
  const renderTokenRef = useRef(0);

  // Pulled off `queue` first only so the memo's deps are plain identifiers:
  // exhaustive-deps can't verify member expressions like `queue.consoleStems`
  // and asks for the whole hook result instead. Both are already stable
  // (useMemo/useCallback), so this changes nothing about when the memo runs.
  const { consoleStems, fixesForStem } = queue;

  /** Identifies a row's enabled chain, so a rendered take can be reused until it changes. */
  const fixSignature = useMemo(() => {
    const signatures: Record<number, string> = {};
    for (const stem of consoleStems) {
      signatures[stem.id] = chainSignature(fixesForStem(stem.id));
    }
    return signatures;
  }, [consoleStems, fixesForStem]);

  /** The takes the rows should be playing right now — never evicted. */
  const currentTakeKeys = useMemo(
    () =>
      new Set(
        Object.entries(fixSignature)
          .filter(([, signature]) => signature)
          .map(([id, signature]) => takeKey(Number(id), signature))
      ),
    [fixSignature]
  );
  const currentTakeKeysRef = useRef(currentTakeKeys);
  useLayoutEffect(() => {
    currentTakeKeysRef.current = currentTakeKeys;
  }, [currentTakeKeys]);

  const effectiveBuffers = useMemo(() => {
    if (bypassFixes) return buffers;
    const merged: Record<number, AudioBuffer> = { ...buffers };
    for (const [id, signature] of Object.entries(fixSignature)) {
      // A row whose chain has no take yet falls back to the raw audio rather
      // than playing something the queue no longer describes.
      const take = signature ? takes.get(takeKey(Number(id), signature)) : undefined;
      if (take) merged[Number(id)] = take;
    }
    return merged;
  }, [buffers, takes, fixSignature, bypassFixes]);

  const playback = useStemPlayback(
    queue.consoleStems,
    effectiveBuffers,
    controls,
    serverMaxDuration
  );
  // play() silently does nothing with no decoded buffers, so the transport has
  // to stay disabled until at least one has landed.
  const playbackReady = Object.keys(buffers).length > 0;

  /** Where the rows' playback audio is, until every row that plays has decoded. */
  const audioLoading = useMemo(() => {
    const wanted = targets.filter((t) => t.id !== FULL_MIX_STEM_ID || fullMixAudible);
    const pending = wanted.filter((t) => !buffers[t.id]);
    if (pending.length === 0) return null;
    // A byte fraction only means something when every pending row has a size.
    let loaded = 0;
    let total = 0;
    let sized = true;
    for (const t of pending) {
      const p = audioProgress[t.id];
      if (!p?.total) {
        sized = false;
      } else {
        loaded += p.loaded;
        total += p.total;
      }
    }
    return {
      ready: wanted.length - pending.length,
      total: wanted.length,
      fraction: sized && total > 0 ? loaded / total : null,
    };
  }, [targets, fullMixAudible, buffers, audioProgress]);

  /** Whether a row can be heard with the current mute/solo. */
  const anySolo = Object.values(controls).some((c) => c.solo);
  const isAudible = (id: number) => {
    const c = controls[id];
    if (!c || c.mute) return false;
    return anySolo ? c.solo : true;
  };

  /** Rows with enabled fixes whose rendered audio does not match them yet. */
  const staleRows = (onlyAudible: boolean): StemInfo[] =>
    queue.consoleStems.filter((stem) => {
      const signature = fixSignature[stem.id];
      if (!signature) return false; // no enabled fixes — the raw audio is correct
      if (onlyAudible && !isAudible(stem.id)) return false;
      return !takes.has(takeKey(stem.id, signature));
    });

  const unrenderedRows = staleRows(true);
  const withFixes =
    !bypassFixes &&
    unrenderedRows.length === 0 &&
    queue.consoleStems.some((stem) => fixSignature[stem.id] && isAudible(stem.id));

  /**
   * Render rows through their fix chains and decode the results.
   *
   * On the server every chain goes through one cache, so a row the warm render
   * already did comes straight back — this is where "fixes render once" pays
   * off for playback.
   */
  /**
   * Render one take and decode it, or join the render already on its way.
   * `chain` is omitted for the row's current chain.
   */
  const loadTake = (rowId: number, signature: string, chain?: ChainStep[]) => {
    const key = takeKey(rowId, signature);
    const pending = pendingTakesRef.current.get(key);
    if (pending) return pending;
    const load = (async () => {
      const path = await queue.previewStemChain(rowId, chain);
      // The compressed playback copy, not the rendered WAV: ~1.5 MB a stem
      // instead of ~23 MB, which is what made loading take minutes.
      return decodeAudio(`/api/produce/clean/playback?path=${encodeURIComponent(path)}`);
    })();
    pendingTakesRef.current.set(key, load);
    const forget = () => pendingTakesRef.current.delete(key);
    void load.then(forget, forget);
    return load;
  };

  const commitTakes = (rendered: (readonly [string, AudioBuffer])[]) =>
    setTakes((prev) =>
      rendered.reduce(
        (acc, [key, buffer]) => addTake(acc, key, buffer, currentTakeKeysRef.current, MAX_TAKES),
        prev
      )
    );

  const renderRows = (rows: StemInfo[], onEach?: () => void) =>
    mapWithConcurrency(rows, RENDER_CONCURRENCY, async (stem) => {
      const signature = fixSignature[stem.id];
      const buffer = await loadTake(stem.id, signature);
      onEach?.();
      return [takeKey(stem.id, signature), buffer] as const;
    });

  /**
   * Bring rows' fixed audio in behind the transport, without holding it up.
   *
   * Playback carries on with the original audio meanwhile, and when a render
   * lands mid-play the transport swaps it in at the playhead by itself. Nothing starts while the
   * whole-queue render is running: it is rendering these same chains, and
   * asking for them again is how fixes used to render twice — the completion
   * effect below picks them up from the cache instead.
   */
  const renderInBackground = async (rows: StemInfo[], afterRender = false) => {
    if (renderInProgress) return;
    const pending = rows.filter((row) => !inFlightRef.current.has(row.id));
    if (pending.length === 0) return;

    const token = renderTokenRef.current;
    pending.forEach((row) => inFlightRef.current.add(row.id));
    setPlaybackRendering(Array.from(inFlightRef.current));
    setPlaybackLoad((prev) => ({
      done: prev?.done ?? 0,
      total: (prev?.total ?? 0) + pending.length,
      afterRender: (prev?.afterRender ?? false) || afterRender,
    }));
    try {
      const rendered = await renderRows(pending, () => {
        if (token === renderTokenRef.current) {
          setPlaybackLoad((prev) => prev && { ...prev, done: prev.done + 1 });
        }
      });
      if (token !== renderTokenRef.current) return; // "Play without"
      commitTakes(rendered);
    } catch (err) {
      if (token === renderTokenRef.current) {
        setPlaybackError(`Could not render fixes — playing without them. ${(err as Error).message}`);
      }
    } finally {
      pending.forEach((row) => inFlightRef.current.delete(row.id));
      setPlaybackRendering(Array.from(inFlightRef.current));
      if (inFlightRef.current.size === 0) setPlaybackLoad(null);
    }
  };

  const cancelPlaybackRender = () => {
    renderTokenRef.current += 1;
    inFlightRef.current.clear();
    setPlaybackRendering([]);
    setPlaybackLoad(null);
  };

  const handleTogglePlay = () => {
    if (playback.playing) {
      playback.pause();
      return;
    }
    // It plays at once; anything not rendered yet follows as it lands.
    void playback.play();
    void renderInBackground(staleRows(true));
  };

  // The warm render finished: every chain it did is in the server's cache, and
  // it made their compressed copies, so fetching the audible rows now costs a
  // lookup and a small download — shown as the render's own last step.
  useEffect(() => {
    if (renderJob.status !== 'complete') return;
    void renderInBackground(staleRows(true), true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [renderJob.status]);

  // While playing, a row that becomes audible or has a fix toggled renders in
  // the background. Keyed on which tools are on, not their params, so dragging
  // a slider in the Adjust drawer does not start a render per step.
  const audibleKey = queue.consoleStems.filter((s) => isAudible(s.id)).map((s) => s.id).join(',');
  const enabledKey = queue.consoleStems
    .map((s) => `${s.id}:${fixesForStem(s.id).filter((f) => f.enabled).map((f) => f.tool).join('+')}`)
    .join('|');
  useEffect(() => {
    if (!playback.playing) return;
    void renderInBackground(staleRows(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playback.playing, audibleKey, enabledKey]);

  // Render the selected row's takes one ON/OFF away, quietly and one at a
  // time, so the next toggle swaps in at once instead of waiting on a render.
  // Not while the whole-queue render runs: it is busy with the same CPU.
  const selectedRowId = queue.selectedStemId;
  const selectedSignature = selectedRowId != null ? fixSignature[selectedRowId] : undefined;
  useEffect(() => {
    if (selectedRowId == null || renderInProgress) return;
    const token = renderTokenRef.current;
    const timer = setTimeout(() => {
      const wanted = neighbourChains(
        fixesForStem(selectedRowId),
        (f) => queue.missingParamsFor(f).length > 0
      ).filter((n) => !takesRef.current.has(takeKey(selectedRowId, n.signature)));
      void mapWithConcurrency(wanted, 1, async (n) => {
        try {
          const buffer = await loadTake(selectedRowId, n.signature, n.chain);
          if (token === renderTokenRef.current) {
            commitTakes([[takeKey(selectedRowId, n.signature), buffer]]);
          }
        } catch {
          // Only a head start: a toggle onto this take renders it as usual.
        }
      });
    }, NEIGHBOUR_DELAY_MS);
    return () => clearTimeout(timer);
    // `loadTake`/`commitTakes` are redefined every render and read refs; the
    // row and its chain are what decide which takes are wanted.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRowId, selectedSignature, renderInProgress]);

  // A fix is heard by playing the song and switching it: while playing, a
  // toggle re-renders the row in the background (above) and swaps in at the
  // playhead, and the open row's other takes are rendered ahead of time.
  const setControl = (id: number, patch: Partial<StemPlaybackControl>) => {
    setControls((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  // --- the task panel -------------------------------------------------------
  const separationRunning = queue.separationTask?.status === 'running';
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!separationRunning) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [separationRunning]);

  const rowName = (id: number) => {
    const stem = queue.consoleStems.find((s) => s.id === id);
    return stem ? stemLabel(stem) : 'row';
  };

  const tasks = buildTasks({
    separation: queue.separationTask,
    analysis: queue.analysisTask,
    render: renderJob,
    playback:
      playbackLoad && playbackRendering.length > 0
        ? { ...playbackLoad, rows: playbackRendering.map(rowName) }
        : null,
    now,
  });

  const handleCancelTask = async (id: TaskId) => {
    setTaskError(null);
    try {
      if (id === 'separate') await queue.cancelSeparation();
      else if (id === 'analyze') await queue.cancelAnalysis();
      else if (id === 'playback') cancelPlaybackRender();
      // Finished on the server but still loading into the console: stop the
      // loading, and play the original audio.
      else if (id === 'render' && renderJob.status !== 'running') cancelPlaybackRender();
      // A save riding on a render stops being a save; the render carries on
      // and stays cached, and its own Cancel stops that too.
      else if (id === 'render') await onCancelRender(renderJob.preview === false);
    } catch (err) {
      setTaskError((err as Error).message);
    }
  };

  const handleRetryTask = (id: TaskId) => {
    setTaskError(null);
    if (id === 'render') void warmRender().then(onRenderStarted);
    else void queue.startAnalysis();
  };

  const handleDismissTasks = () => {
    queue.dismissTasks();
    if (renderJob.status !== 'running' && renderJob.status !== 'idle') onDismissRender();
  };

  // A stem set can be showing (preloaded from an earlier session) before any
  // analysis pass has ever run for it — the fix queue/results only make sense
  // once a pass has completed, is in flight, or a single row has been analyzed
  // on its own.
  const hasEverAnalyzed = queue.analyzed || queue.analyzing || queue.analyzedStemIds.size > 0;
  const fullMixPeaks = peaks[FULL_MIX_STEM_ID]?.peaks ?? null;

  if (versions.length === 0) {
    return <p className="text-sm text-text/50">No versions yet for this song.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <VersionDetails
        version={selectedVersion}
        renderInProgress={renderInProgress}
        canDelete={versions.length > 1}
        busy={selectedVersion != null && versionActions.busyId === selectedVersion.id}
        onSetDefault={() => selectedVersion && versionActions.onSetDefault(selectedVersion.id)}
        onRename={(name) => selectedVersion && versionActions.onRename(selectedVersion.id, name)}
        onDelete={() =>
          selectedVersion && versionActions.onDelete(selectedVersion.id, selectedVersion.name)
        }
        onStartAnalysis={queue.startAnalysis}
        onAnalyzeAndSave={queue.analyzeAndSave}
        onSeparateStems={queue.separateStems}
        analyzing={queue.analyzing}
        savingAfterAnalysis={queue.savingAfterAnalysis}
        separating={queue.separating}
        analysisNote={queue.analysisNote}
        hasStems={queue.stems.length > 0}
      >
        {/* The player shows once there are rows to play: the stems are what
            it plays, the full mix only when that row is un-muted. */}
        {queue.stems.length > 0 && (
          <TransportBar
            peaks={fullMixPeaks}
            peaksLoading={!fullMixPeaks && peaksLoadingIds.has(FULL_MIX_STEM_ID)}
            playbackReady={playbackReady}
            audioLoading={audioLoading}
            playing={playback.playing}
            playhead={playback.playhead}
            maxDuration={playback.maxDuration}
            onTogglePlay={handleTogglePlay}
            onSeek={playback.seek}
            unrenderedRows={unrenderedRows.map(stemLabel)}
            renderingFixes={renderInProgress || playbackRendering.length > 0}
            withFixes={withFixes}
            songId={songId}
            fixesBypassed={bypassFixes}
            onToggleBypass={queue.fixes.length > 0 ? () => setBypassFixes((b) => !b) : undefined}
          />
        )}
      </VersionDetails>

      {queue.error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {queue.error}
        </div>
      )}
      {taskError && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {taskError}
        </div>
      )}
      {peaksError && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {peaksError}
        </div>
      )}
      {/* Kept quieter than a waveform failure: the console is fully usable for
          reviewing and accepting fixes, it just can't play them back. */}
      {playbackError && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 text-amber-200 rounded-lg text-sm">
          Playback audio unavailable — {playbackError}
        </div>
      )}

      {/* Lyrics and (once a stem set exists) the stem console both render
          independently of whether analysis has ever been run — a stem set
          or a lyric sheet saved in an earlier session shows immediately on
          mount instead of waiting behind "Start analysis". */}
      <div className="grid gap-4 lg:grid-cols-[1fr_360px] items-start">
        <div className="flex flex-col gap-4 min-w-0">
          {queue.stems.length === 0 && !queue.analyzing && (
            <p className="text-sm text-text/45 py-6 text-center">
              {queue.stemsOnAnotherVersion ? (
                <>
                  The stems on this song were separated from a{' '}
                  <span className="text-text/70 font-medium">different version</span>, so they are
                  not this one&apos;s to review. Press{' '}
                  <span className="text-text/70 font-medium">Start analysis</span> above to separate
                  the version you have selected.
                </>
              ) : (
                <>
                  Press <span className="text-text/70 font-medium">Start analysis</span> above — it
                  separates this version into stems, then measures each one on its own.
                </>
              )}
            </p>
          )}

          {queue.stems.length === 0 && queue.analyzing && (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <div className="w-6 h-6 rounded-full border-2 border-signal/30 border-t-signal animate-spin" />
              <p className="text-sm text-text/60">
                {queue.analysisNote ?? 'Analyzing…'}
              </p>
            </div>
          )}

          {/* Stays mounted (showing the previous run's stems) through a
              re-separate/re-analyze, instead of the whole console vanishing
              back to the empty-state prompt above. */}
          {queue.stems.length > 0 && (
            <StemConsole
              stems={queue.consoleStems}
              peaks={peaks}
              peaksLoadingIds={peaksLoadingIds}
              controls={controls}
              setControl={setControl}
              selectedStemId={queue.selectedStemId}
              onSelectStem={queue.setSelectedStemId}
              fixesForStem={queue.fixesForStem}
              onSetRowFixesEnabled={queue.setRowFixesEnabled}
              renderFixes={(stem) =>
                hasEverAnalyzed ? (
                  <FixQueue
                    fixes={queue.fixesForStem(stem.id)}
                    analyzing={queue.analyzing}
                    addableTools={queue.addableToolsForStem(stem.id)}
                    onToggle={queue.toggleFix}
                    onAdjust={setDrawerFix}
                    onAddFix={(tool) => queue.addManualFix(stem.id, tool)}
                    missingParamsFor={queue.missingParamsFor}
                    onRemoveFix={queue.removeFix}
                  />
                ) : (
                  <p className="text-sm text-text/45">
                    Loaded from a previous run — press{' '}
                    <span className="text-text/70 font-medium">Start analysis</span> above, or
                    analyze this row on its own, to detect its fixes.
                  </p>
                )
              }
              analyzedStemIds={queue.analyzedStemIds}
              analyzingStemIds={queue.analyzingStemIds}
              onAnalyzeStem={queue.analyzeStem}
              identifyingStemIds={queue.identifyingStemIds}
              onIdentifyStem={queue.identifyStem}
              onRenameStem={queue.renameStem}
              playhead={playback.playhead}
              maxDuration={playback.maxDuration}
              onSeek={playback.seek}
              separating={queue.analyzing || queue.separating}
              analyzed={queue.analyzed}
              analysisNote={queue.analysisNote}
            />
          )}
        </div>

        <div className="flex flex-col gap-4">
          {hasEverAnalyzed && (
            <ResultSidebar
              enabledCount={queue.enabledCount}
              totalCount={queue.fixes.length}
              onAcceptAll={async () => {
                // A save's notices are not in this response — the render has
                // barely begun. The task panel reports them when it lands.
                await queue.acceptAll(false);
                onRenderStarted();
              }}
              onPreviewFull={async () => {
                const job = await queue.acceptAll(true);
                onRenderStarted();
                return {
                  path: job.candidate_path as string,
                  notices: job.notices,
                };
              }}
              onAccepted={onApplied}
              renderInProgress={renderInProgress}
            />
          )}
          <LyricsCard songId={songId} />
        </div>
      </div>

      <TaskPanel
        tasks={tasks}
        onCancel={(id) => void handleCancelTask(id)}
        onRetry={handleRetryTask}
        onDismiss={handleDismissTasks}
      />

      {drawerFix && (
        <AdvancedDrawer
          fix={drawerFix}
          paramsMeta={queue.toolParamsByTool[drawerFix.tool] || []}
          onChange={(patch) => {
            queue.updateFixParams(drawerFix.id, patch);
            setDrawerFix((prev) =>
              prev && prev.id === drawerFix.id
                ? { ...prev, currentParams: { ...prev.currentParams, ...patch } }
                : prev
            );
          }}
          onReset={() => {
            queue.resetFixParams(drawerFix.id);
            setDrawerFix((prev) =>
              prev && prev.id === drawerFix.id ? { ...prev, currentParams: { ...prev.suggestedParams } } : prev
            );
          }}
          onClose={() => setDrawerFix(null)}
        />
      )}
    </div>
  );
}
