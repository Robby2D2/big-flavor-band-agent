'use client';

import { useEffect, useRef, useState } from 'react';
import {
  useProcessingQueue,
  FixEntry,
  FULL_MIX_STEM_ID,
  stemLabel,
} from '@/hooks/useProcessingQueue';
import { decodeAudio, Region } from '../audioEngine';
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

  const [buffers, setBuffers] = useState<Record<number, AudioBuffer>>({});
  const [loadingStemIds, setLoadingStemIds] = useState<Set<number>>(new Set());
  const [controls, setControls] = useState<Record<number, StemPlaybackControl>>({});
  const [region, setRegion] = useState<Region | null>(null);
  const [drawerFix, setDrawerFix] = useState<FixEntry | null>(null);
  const [decodeError, setDecodeError] = useState<string | null>(null);

  // Decode the full mix and each stem once, for the transport, the console
  // sparklines, playback, and the selected row's detail waveform. Decoding is
  // fanned out rather than run one after another — a full stem set is several
  // whole-song files, and serially they took long enough that the console sat
  // there looking empty.
  const decodedUrls = useRef<Map<number, string>>(new Map());
  const stemIdsKey = queue.stems.map((s) => s.id).join(',');
  useEffect(() => {
    if (sourceVersionId == null) return;
    const targets = [
      { id: FULL_MIX_STEM_ID, url: `/api/produce/versions/${sourceVersionId}/audio` },
      ...queue.stems.map((s) => ({ id: s.id, url: `/api/produce/stems/${s.id}/audio` })),
    ];
    const targetIds = new Set(targets.map((t) => t.id));

    // Drop anything that is no longer a console row (a re-separation replacing
    // the stem set), and keep what is still current — including the user's
    // mute/solo/gain for rows that survived.
    for (const id of Array.from(decodedUrls.current.keys())) {
      if (!targetIds.has(id)) decodedUrls.current.delete(id);
    }
    setBuffers((prev) =>
      Object.fromEntries(Object.entries(prev).filter(([id]) => targetIds.has(Number(id))))
    );
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

    const pending = targets.filter((t) => decodedUrls.current.get(t.id) !== t.url);
    if (pending.length === 0) return;

    let cancelled = false;
    setDecodeError(null);
    setLoadingStemIds(new Set(pending.map((t) => t.id)));
    void Promise.all(
      pending.map(async (t) => {
        try {
          const buffer = await decodeAudio(t.url);
          if (cancelled) return;
          decodedUrls.current.set(t.id, t.url);
          setBuffers((prev) => ({ ...prev, [t.id]: buffer }));
        } catch (err) {
          if (!cancelled) setDecodeError((err as Error).message);
        } finally {
          if (!cancelled) {
            setLoadingStemIds((prev) => {
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
    // `stemIdsKey` stands in for queue.stems: a fresh array arrives on every
    // analysis pass, but only a different set of stem ids should re-decode.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceVersionId, stemIdsKey]);

  useEffect(() => {
    queue.ensureToolParams();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue.analyzed]);

  const playback = useStemPlayback(queue.consoleStems, buffers, controls);

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
      />

      {queue.error && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {queue.error}
        </div>
      )}
      {decodeError && (
        <div className="p-3 bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg text-sm">
          {decodeError}
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
                buffers={buffers}
                loadingStemIds={loadingStemIds}
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
                onTogglePlay={playback.toggle}
                onSeek={playback.seek}
                separating={queue.analyzing}
                analyzed={queue.analyzed}
                analysisNote={queue.analysisNote}
                onReseparate={queue.reseparateAndAnalyze}
              />

              {selectedStem && (
                <StemDetailPanel
                  stemId={selectedStem.id}
                  stemName={stemLabel(selectedStem)}
                  sourceName={selectedStem.name}
                  audioSrc={
                    fullMixSelected
                      ? `/api/produce/versions/${sourceVersionId}/audio`
                      : `/api/produce/stems/${selectedStem.id}/audio`
                  }
                  buffer={buffers[selectedStem.id] ?? null}
                  duration={playback.maxDuration}
                  region={region}
                  onRegionChange={setRegion}
                  enabledFixCount={enabledSelectedStemFixCount}
                  onPreviewChain={() => queue.previewStemChain(selectedStem.id)}
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
