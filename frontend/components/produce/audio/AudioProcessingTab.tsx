'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  useProcessingQueue,
  FixEntry,
  FULL_MIX_STEM_ID,
  stemLabel,
} from '@/hooks/useProcessingQueue';
import { decodeAudio, fetchPeaks, Region, WaveformPeaks } from '../audioEngine';
import type { StemPlaybackControl } from './useStemPlayback';
import { useStemPlayback } from './useStemPlayback';
import VersionBar from './VersionBar';
import StemConsole from './StemConsole';
import StemDetailPanel from './StemDetailPanel';
import FixQueue from './FixQueue';
import AdvancedDrawer from './AdvancedDrawer';
import ResultSidebar from './ResultSidebar';
import LyricsCard from './LyricsCard';

interface VersionOption {
  id: number;
  name: string;
  is_published: boolean;
}

interface AudioProcessingTabProps {
  songId: number;
  versions: VersionOption[];
  onApplied: () => void;
  onManageVersions: () => void;
}

/**
 * The redesigned Audio processing tab: pick a version, run one analysis pass,
 * then review a queue of detected fixes (one card per fix, pre-filled with
 * the tool's own real measured numbers) grouped by stem, and accept the ones
 * you want as a single new version. Replaces the old per-tool checkbox list
 * (MultitrackEditor) — the interaction model is different enough that a new
 * component tree was cleaner than patching the old one.
 */
export default function AudioProcessingTab({
  songId,
  versions,
  onApplied,
  onManageVersions,
}: AudioProcessingTabProps) {
  const [sourceVersionId, setSourceVersionId] = useState<number | null>(null);

  useEffect(() => {
    setSourceVersionId((prev) => {
      if (prev != null && versions.some((v) => v.id === prev)) return prev;
      const published = versions.find((v) => v.is_published);
      return published?.id ?? versions[0]?.id ?? null;
    });
  }, [versions]);

  const queue = useProcessingQueue(songId, sourceVersionId);

  const [peaks, setPeaks] = useState<Record<number, WaveformPeaks>>({});
  const [peaksLoadingIds, setPeaksLoadingIds] = useState<Set<number>>(new Set());
  const [peaksError, setPeaksError] = useState<string | null>(null);
  const [buffers, setBuffers] = useState<Record<number, AudioBuffer>>({});
  const [controls, setControls] = useState<Record<number, StemPlaybackControl>>({});
  const [region, setRegion] = useState<Region | null>(null);
  const [drawerFix, setDrawerFix] = useState<FixEntry | null>(null);
  const [playbackError, setPlaybackError] = useState<string | null>(null);

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
        try {
          const buffer = await decodeAudio(t.audio);
          if (cancelled) {
            decodedUrls.current.delete(t.id);
            return;
          }
          setBuffers((prev) => ({ ...prev, [t.id]: buffer }));
        } catch (err) {
          decodedUrls.current.delete(t.id);
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
  // What the transport plays for each row: its rendered fix chain when the row
  // has enabled fixes, otherwise the raw audio. The transport is the only
  // player on the page, so "with fixes" has to be what you simply hear rather
  // than a mode you switch into.
  const [fixedBuffers, setFixedBuffers] = useState<
    Record<number, { signature: string; buffer: AudioBuffer }>
  >({});
  const [renderingFixes, setRenderingFixes] = useState(false);

  /** Identifies a row's enabled chain, so a rendered take can be reused until it changes. */
  const fixSignature = useMemo(() => {
    const signatures: Record<number, string> = {};
    for (const stem of queue.consoleStems) {
      const enabled = queue
        .fixesForStem(stem.id)
        .filter((f) => f.enabled)
        .map((f) => ({ tool: f.tool, params: f.currentParams }));
      signatures[stem.id] = enabled.length ? JSON.stringify(enabled) : '';
    }
    return signatures;
  }, [queue.consoleStems, queue.fixesForStem]);

  const effectiveBuffers = useMemo(() => {
    const merged: Record<number, AudioBuffer> = { ...buffers };
    for (const [id, rendered] of Object.entries(fixedBuffers)) {
      // A stale take (the chain changed since it was rendered) falls back to the
      // raw audio rather than playing something the queue no longer describes.
      if (rendered.signature && rendered.signature === fixSignature[Number(id)]) {
        merged[Number(id)] = rendered.buffer;
      }
    }
    return merged;
  }, [buffers, fixedBuffers, fixSignature]);

  const playback = useStemPlayback(
    queue.consoleStems,
    effectiveBuffers,
    controls,
    serverMaxDuration
  );
  // play() silently does nothing with no decoded buffers, so the transport has
  // to stay disabled until at least one has landed.
  const playbackReady = Object.keys(buffers).length > 0;

  const playWhenRenderedRef = useRef(false);

  /**
   * Render any row whose enabled chain isn't already decoded, then start playback.
   *
   * Chain-applying is real DSP on the server, so it happens on demand at play
   * time rather than on every toggle in the fix queue — pressing play is the
   * point where the producer has actually asked to hear the result.
   */
  const handleTogglePlay = async () => {
    if (playback.playing) {
      playback.pause();
      return;
    }

    const stale = queue.consoleStems.filter((stem) => {
      const signature = fixSignature[stem.id];
      if (!signature) return false; // no enabled fixes — the raw audio is correct
      return fixedBuffers[stem.id]?.signature !== signature;
    });

    if (stale.length === 0) {
      void playback.play();
      return;
    }

    setRenderingFixes(true);
    setPlaybackError(null);
    try {
      const rendered = await Promise.all(
        stale.map(async (stem) => {
          const signature = fixSignature[stem.id];
          const path = await queue.previewStemChain(stem.id);
          const buffer = await decodeAudio(
            `/api/produce/clean/preview?path=${encodeURIComponent(path)}`
          );
          return [stem.id, { signature, buffer }] as const;
        })
      );
      // Start playing from the effect below rather than here: `playback.play`
      // closes over the buffers of the render it came from, so calling it now
      // would play the pre-render audio we just replaced.
      playWhenRenderedRef.current = true;
      setFixedBuffers((prev) => ({ ...prev, ...Object.fromEntries(rendered) }));
    } catch (err) {
      // Fall through to playing what we have: the raw stems are still a
      // truthful rendition of the song, just without the pending fixes.
      setPlaybackError(`Could not render fixes — playing without them. ${(err as Error).message}`);
      void playback.play();
    } finally {
      setRenderingFixes(false);
    }
  };

  useEffect(() => {
    if (!playWhenRenderedRef.current) return;
    playWhenRenderedRef.current = false;
    void playback.play();
    // Only the freshly committed buffers should trigger this; `playback` is
    // deliberately not a dependency, since its identity changes on every tick
    // of the playhead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveBuffers]);

  const setControl = (id: number, patch: Partial<StemPlaybackControl>) => {
    setControls((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  };

  useEffect(() => {
    setRegion(null);
  }, [queue.selectedStemId]);

  const selectedStem = queue.consoleStems.find((s) => s.id === queue.selectedStemId) ?? null;
  const fullMixSelected = queue.selectedStemId === FULL_MIX_STEM_ID;
  const selectedStemFixes = queue.selectedStemId != null ? queue.fixesForStem(queue.selectedStemId) : [];
  const enabledSelectedStemFixCount = selectedStemFixes.filter((f) => f.enabled).length;
  // A stem set can be showing (preloaded from an earlier session) before any
  // analysis pass has ever run for it — the fix queue/results only make sense
  // once a pass has completed, is in flight, or a single row has been analyzed
  // on its own.
  const hasEverAnalyzed = queue.analyzed || queue.analyzing || queue.analyzedStemIds.size > 0;

  if (versions.length === 0) {
    return <p className="text-sm text-text/50">No versions yet for this song.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <VersionBar
        versions={versions}
        sourceVersionId={sourceVersionId}
        onChangeSource={setSourceVersionId}
        onStartAnalysis={queue.startAnalysis}
        onManageVersions={onManageVersions}
        analyzing={queue.analyzing}
        analysisNote={queue.analysisNote}
        hasStems={queue.stems.length > 0}
      />

      {queue.error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {queue.error}
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
              Press <span className="text-text/70 font-medium">Start analysis</span> above — it
              separates the song into stems, then measures each one on its own.
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
            <>
              <StemConsole
                stems={queue.consoleStems}
                peaks={peaks}
                peaksLoadingIds={peaksLoadingIds}
                playbackReady={playbackReady}
                controls={controls}
                setControl={setControl}
                selectedStemId={queue.selectedStemId}
                onSelectStem={queue.setSelectedStemId}
                fixesForStem={queue.fixesForStem}
                analyzedStemIds={queue.analyzedStemIds}
                analyzingStemIds={queue.analyzingStemIds}
                onAnalyzeStem={queue.analyzeStem}
                identifyingStemIds={queue.identifyingStemIds}
                onIdentifyStem={queue.identifyStem}
                onRenameStem={queue.renameStem}
                playing={playback.playing}
                playhead={playback.playhead}
                maxDuration={playback.maxDuration}
                onTogglePlay={handleTogglePlay}
                renderingFixes={renderingFixes}
                onSeek={playback.seek}
                separating={queue.analyzing}
                analyzed={queue.analyzed}
                analysisNote={queue.analysisNote}
                onReseparate={queue.reseparateAndAnalyze}
              />

              {selectedStem && (
                <StemDetailPanel
                  stemName={stemLabel(selectedStem)}
                  sourceName={selectedStem.name}
                  peaks={peaks[selectedStem.id]?.peaks ?? null}
                  duration={playback.maxDuration}
                  region={region}
                  onRegionChange={setRegion}
                  enabledFixCount={enabledSelectedStemFixCount}
                />
              )}

              {hasEverAnalyzed ? (
                <FixQueue
                  stemName={selectedStem ? stemLabel(selectedStem) : null}
                  scopeLabel={fullMixSelected ? 'FULL MIX' : 'THIS STEM'}
                  stemFixes={selectedStemFixes}
                  // The full-mix row already *is* the master bucket — don't
                  // list the same fixes twice when it's selected.
                  masterFixes={fullMixSelected ? [] : queue.masterFixes}
                  analyzing={queue.analyzing}
                  onToggle={queue.toggleFix}
                  onAdjust={setDrawerFix}
                  onHear={queue.previewSingleFix}
                />
              ) : (
                <p className="text-sm text-text/45 py-4 text-center">
                  Loaded from a previous run — press{' '}
                  <span className="text-text/70 font-medium">Start analysis</span> above to detect
                  fixes for these stems.
                </p>
              )}
            </>
          )}
        </div>

        <div className="flex flex-col gap-4">
          {hasEverAnalyzed && (
            <ResultSidebar
              enabledCount={queue.enabledCount}
              totalCount={queue.fixes.length}
              onAcceptAll={() => queue.acceptAll(false)}
              onPreviewFull={async () => {
                const data = await queue.acceptAll(true);
                return data.candidate_path as string;
              }}
              onAccepted={onApplied}
            />
          )}
          <LyricsCard songId={songId} />
        </div>
      </div>

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
