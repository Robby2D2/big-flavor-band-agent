'use client';

import {
  formatBytes,
  formatDuration,
  formatProducedAt,
  formatSteps,
} from '@/lib/formatVersion';
import {
  UnsavedRender,
  unsavedRenderAudioUrl,
  unsavedRenderLabel,
} from '@/lib/unsavedRender';

export interface VersionDetail {
  id: number;
  name: string;
  label: string;
  is_published: boolean;
  steps_applied: { step: string }[] | null;
  aggressiveness: string | null;
  duration_seconds: number | null;
  file_size_bytes: number | null;
  created_at: string | null;
}

interface VersionDetailsProps {
  version: VersionDetail | null;
  /** Set instead of `version` when the unsaved-render row is selected. */
  unsavedRender?: UnsavedRender | null;
  /** A render is in flight — nothing that would start another may be pressed. */
  renderInProgress?: boolean;
  /** False for the last remaining version — deleting it would leave none. */
  canDelete: boolean;
  /** A rename/delete/set-default request for this version is in flight. */
  busy: boolean;
  onSetDefault: () => void;
  onRename: () => void;
  onDelete: () => void;
  onStartAnalysis: () => void;
  /** Separate this version into stems without measuring anything. */
  onSeparateStems: () => void;
  analyzing: boolean;
  separating?: boolean;
  analysisNote: string | null;
  /** This version already has stems, so an analysis pass only measures them. */
  hasStems: boolean;
}

/**
 * Everything you can do to one version, in one place.
 *
 * Selecting happens in the list above; this panel is the selection's detail
 * view. Auditioning, renaming, deleting and setting the default used to be
 * buttons crammed into each table row, separate from Start analysis down here,
 * so the same version was acted on from two different places depending on which
 * verb you wanted.
 */
export default function VersionDetails({
  version,
  unsavedRender,
  renderInProgress = false,
  canDelete,
  busy,
  onSetDefault,
  onRename,
  onDelete,
  onStartAnalysis,
  onSeparateStems,
  analyzing,
  separating = false,
  analysisNote,
  hasStems,
}: VersionDetailsProps) {
  // The mix Start analysis rendered, before anyone has decided to keep it.
  // There is no version id behind it, so the only thing to do here is listen:
  // saving is still "Accept all & save version" in the result panel.
  if (unsavedRender) {
    return (
      <div className="bg-raised border border-signal/30 rounded-xl p-4 flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
              Auditioning
            </div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-semibold text-text">New mix</span>
              <span className="font-mono text-[10px] text-amber-400">NOT SAVED</span>
            </div>
            <div className="text-xs text-text/45 mt-1">{unsavedRenderLabel(unsavedRender)}</div>
          </div>

          <audio
            controls
            preload="none"
            src={unsavedRenderAudioUrl(unsavedRender.candidatePath)}
            className="h-8 w-56 flex-none"
          />
        </div>

        <p className="font-mono text-xs text-text/35">
          compare it with the original above · keep it with “Accept all &amp; save version”
        </p>
      </div>
    );
  }

  if (!version) {
    return (
      <div className="bg-raised border border-white/8 rounded-xl p-4">
        <p className="text-sm text-text/45">
          Select a version above to audition it, rename it, or run an analysis.
        </p>
      </div>
    );
  }

  const meta = [
    formatDuration(version.duration_seconds),
    formatBytes(version.file_size_bytes),
    formatProducedAt(version.created_at),
  ]
    .filter((part) => part !== '—')
    .join(' · ');

  const steps = formatSteps(version.steps_applied);

  return (
    <div className="bg-raised border border-white/8 rounded-xl p-4 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
            Working from
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="font-semibold text-text truncate">{version.name}</span>
            {version.is_published && (
              <span className="font-mono text-[10px] text-signal">DEFAULT</span>
            )}
            {version.label === 'original' && (
              <span className="text-xs text-text/35">original</span>
            )}
          </div>
          {meta && <div className="text-xs text-text/45 mt-1">{meta}</div>}
          {steps !== '—' && (
            <div className="text-xs text-text/45 mt-0.5">
              Steps: {steps}
              {version.aggressiveness ? ` · ${version.aggressiveness}` : ''}
            </div>
          )}
        </div>

        <audio
          controls
          preload="none"
          src={`/api/produce/versions/${version.id}/audio`}
          className="h-8 w-56 flex-none"
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onSetDefault}
            disabled={version.is_published || busy}
            className="text-xs px-2.5 py-1.5 bg-signal text-canvas font-semibold rounded-lg hover:opacity-90 disabled:bg-white/10 disabled:text-text/35 disabled:cursor-not-allowed"
          >
            {version.is_published ? 'Is default' : 'Set default'}
          </button>
          <button
            onClick={onRename}
            disabled={busy}
            className="text-xs px-2.5 py-1.5 border border-white/14 rounded-lg text-text/70 hover:bg-white/5 disabled:opacity-50"
          >
            Rename
          </button>
          <button
            onClick={onDelete}
            disabled={busy || !canDelete || renderInProgress}
            title={
              renderInProgress
                ? 'Wait for the render to finish'
                : canDelete
                  ? undefined
                  : 'A song keeps at least one version'
            }
            className="text-xs px-2.5 py-1.5 border border-red-300 dark:border-red-700 rounded-lg text-red-600 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Delete
          </button>
        </div>

        {/* The two jobs, side by side: making the parts, and measuring them.
            Separating used to be reachable only from inside the console, which
            meant a version with no stems could not be separated without
            committing to a full measuring pass first. */}
        <div className="flex items-center gap-2">
          <button
            onClick={onSeparateStems}
            disabled={analyzing || separating || renderInProgress}
            title={
              hasStems
                ? 'Separate this version again, replacing the stems it has'
                : 'Separate this version into stems, without measuring them'
            }
            className="px-3 py-2 border border-white/14 text-text/75 font-semibold text-sm rounded-lg hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {separating ? 'Separating…' : 'Separate stems'}
          </button>
          <button
            onClick={onStartAnalysis}
            disabled={analyzing || separating || renderInProgress}
            className="px-4 py-2 bg-signal text-canvas font-semibold text-sm rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {analyzing ? 'Analyzing…' : 'Start analysis'}
          </button>
        </div>
      </div>

      {renderInProgress ? (
        <p className="font-mono text-xs text-text/40">
          rendering the current queue · actions are paused until it finishes
        </p>
      ) : analysisNote ? (
        <p className="font-mono text-xs text-text/40">{analysisNote}</p>
      ) : (
        /* Says which of the two jobs a press will actually do: with stems already
           on disk, analysis never re-separates — that is Separate stems' job. */
        <p className="font-mono text-xs text-text/35">
          {hasStems
            ? 'analysis measures the stems this version already has · separate stems makes a fresh set'
            : 'this version has no stems yet · either button separates it first · takes a minute or two'}
        </p>
      )}
    </div>
  );
}
