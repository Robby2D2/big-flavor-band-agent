'use client';

import { ReactNode, useEffect, useRef, useState } from 'react';
import {
  formatBytes,
  formatDuration,
  formatProducedAt,
  formatSteps,
} from '@/lib/formatVersion';

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
  /** A render is in flight — nothing that would start another may be pressed. */
  renderInProgress?: boolean;
  /** False for the last remaining version — deleting it would leave none. */
  canDelete: boolean;
  /** A rename/delete/set-default request for this version is in flight. */
  busy: boolean;
  onSetDefault: () => void;
  onRename: (name: string) => void;
  onDelete: () => void;
  onStartAnalysis: () => void;
  /** Analyze, then save every recommended fix as a new version — one press. */
  onAnalyzeAndSave: () => void;
  /** Separate this version into stems without measuring anything. */
  onSeparateStems: () => void;
  analyzing: boolean;
  /** The pass running is Analyze & save. */
  savingAfterAnalysis?: boolean;
  separating?: boolean;
  analysisNote: string | null;
  /** This version already has stems, so an analysis pass only measures them. */
  hasStems: boolean;
  /** The page's player (TransportBar), once there is something to play. */
  children?: ReactNode;
}

const iconButton =
  'flex-none inline-flex h-7 w-7 items-center justify-center rounded-md text-text/40 hover:bg-white/5 hover:text-text/80 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent';

/**
 * The selected version and its player, in one card.
 *
 * Selecting happens in the list above; this is the selection's detail view and
 * the page's only player. The everyday verbs sit where they usually do — a
 * pencil beside the name, a trash can, a default checkbox — so the one real
 * choice, which job to run, gets the button: Start analysis, with the other
 * two jobs on its menu. The card sticks to the top of the screen on wider
 * displays, so Play and the fixes switch stay at hand while the console scrolls.
 */
export default function VersionDetails({
  version,
  renderInProgress = false,
  canDelete,
  busy,
  onSetDefault,
  onRename,
  onDelete,
  onStartAnalysis,
  onAnalyzeAndSave,
  onSeparateStems,
  analyzing,
  savingAfterAnalysis = false,
  separating = false,
  analysisNote,
  hasStems,
  children,
}: VersionDetailsProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', escape);
    };
  }, [menuOpen]);

  if (!version) {
    return (
      <div className="bg-raised border border-white/8 rounded-xl p-4">
        <p className="text-sm text-text/45">
          Select a version above to play it, rename it, make it the default, or run an analysis.
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
  const jobsLocked = analyzing || separating || renderInProgress;

  const commitRename = () => {
    setEditing(false);
    const name = draft.trim();
    if (name && name !== version.name) onRename(name);
  };

  const runFromMenu = (job: () => void) => {
    setMenuOpen(false);
    job();
  };

  return (
    <div className="md:sticky md:top-0 z-30 bg-raised/95 backdrop-blur border border-white/8 rounded-xl p-3.5 flex flex-col gap-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
            Working from
          </div>
          <div className="flex items-center gap-1.5 mt-0.5 min-w-0">
            {editing ? (
              <input
                ref={inputRef}
                value={draft}
                aria-label="Version name"
                onChange={(e) => setDraft(e.target.value)}
                onBlur={commitRename}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') commitRename();
                  if (e.key === 'Escape') setEditing(false);
                }}
                className="min-w-0 w-64 bg-canvas border border-signal/50 rounded px-1.5 py-0.5 font-semibold text-text outline-none"
              />
            ) : (
              <>
                <span className="font-semibold text-text truncate">{version.name}</span>
                <button
                  onClick={() => {
                    setDraft(version.name);
                    setEditing(true);
                  }}
                  disabled={busy}
                  aria-label="Rename version"
                  title="Rename version"
                  className={iconButton}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
                    <path d="M11.2 2.3a1.5 1.5 0 0 1 2.1 0l.4.4a1.5 1.5 0 0 1 0 2.1L5.6 12.9 2.5 13.5l.6-3.1 8.1-8.1Z" strokeLinejoin="round" />
                  </svg>
                </button>
              </>
            )}
            <button
              onClick={onDelete}
              disabled={busy || !canDelete || renderInProgress}
              aria-label="Delete version"
              title={
                renderInProgress
                  ? 'Wait for the render to finish'
                  : canDelete
                    ? 'Delete version'
                    : 'A song keeps at least one version'
              }
              className={`${iconButton} hover:text-red-400`}
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
                <path d="M2.5 4h11M6 4V2.5h4V4M4 4l.7 9.1a1 1 0 0 0 1 .9h4.6a1 1 0 0 0 1-.9L12 4M6.75 6.5v5M9.25 6.5v5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {version.label === 'original' && (
              <span className="text-xs text-text/35 flex-none">original</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-text/45">
            {/* A song always has exactly one default, so this only ever turns on:
                another version is made the default from its own card. */}
            <label
              className={`flex items-center gap-1.5 ${
                version.is_published ? 'text-signal' : 'cursor-pointer hover:text-text/75'
              }`}
              title={
                version.is_published
                  ? 'This version plays everywhere: radio, search, previews and downloads. To change it, make another version the default.'
                  : 'Play this version everywhere: radio, search, previews and downloads'
              }
            >
              <input
                type="checkbox"
                checked={version.is_published}
                disabled={version.is_published || busy}
                onChange={onSetDefault}
                className="accent-signal"
              />
              Default version
            </label>
            {meta && <span>{meta}</span>}
            {steps !== '—' && (
              <span>
                Steps: {steps}
                {version.aggressiveness ? ` · ${version.aggressiveness}` : ''}
              </span>
            )}
          </div>
        </div>

        {/* One button for the job you usually want, the other two on its menu.
            Separating sits here rather than inside the console so a version with
            no stems can be separated without a full measuring pass. */}
        <div ref={menuRef} className="relative flex flex-none">
          <button
            onClick={onStartAnalysis}
            disabled={jobsLocked}
            title="Measure each stem and list the fixes it needs, for you to review"
            className="px-4 py-2 bg-signal text-canvas font-semibold text-sm rounded-l-lg disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {analyzing ? (savingAfterAnalysis ? 'Analyzing & saving…' : 'Analyzing…') : separating ? 'Separating…' : 'Start analysis'}
          </button>
          <button
            onClick={() => setMenuOpen((open) => !open)}
            disabled={jobsLocked}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label="More analysis options"
            className="px-2 py-2 bg-signal text-canvas rounded-r-lg border-l border-canvas/25 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden>
              <path d="M2.5 4.25 6 7.75l3.5-3.5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          {menuOpen && (
            <div
              role="menu"
              className="absolute right-0 top-full mt-1.5 z-40 w-72 rounded-lg border border-white/12 bg-panel shadow-xl p-1"
            >
              <button
                role="menuitem"
                onClick={() => runFromMenu(onAnalyzeAndSave)}
                className="w-full text-left rounded-md px-3 py-2 hover:bg-white/5"
              >
                <div className="text-sm font-semibold text-text">Analyze &amp; save</div>
                <div className="text-xs text-text/45 mt-0.5">
                  Apply every recommended fix and save the result as a new version. Runs on the
                  server, so you can leave the page.
                </div>
              </button>
              <button
                role="menuitem"
                onClick={() => runFromMenu(onSeparateStems)}
                className="w-full text-left rounded-md px-3 py-2 hover:bg-white/5"
              >
                <div className="text-sm font-semibold text-text">
                  {hasStems ? 'Separate stems again' : 'Separate stems'}
                </div>
                <div className="text-xs text-text/45 mt-0.5">
                  {hasStems
                    ? 'Make a fresh set of stems, replacing the ones this version has. Analysis on its own reuses them.'
                    : 'Split this version into stems without measuring them. Takes a minute or two.'}
                </div>
              </button>
            </div>
          )}
        </div>
      </div>

      {children}

      {(renderInProgress || analysisNote) && (
        <p className="font-mono text-xs text-text/40">
          {renderInProgress
            ? 'rendering the current queue · actions are paused until it finishes'
            : analysisNote}
        </p>
      )}
    </div>
  );
}
