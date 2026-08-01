'use client';

import { useState } from 'react';

interface ResultSidebarProps {
  enabledCount: number;
  totalCount: number;
  onAcceptAll: () => Promise<any>;
  onPreviewFull: () => Promise<string>;
  onAccepted: () => void;
}

/**
 * The single place the review queue resolves to: preview the full render, or
 * accept every enabled fix as one new version. The original is never touched
 * — accepting always creates a new candidate version.
 */
export default function ResultSidebar({
  enabledCount,
  totalCount,
  onAcceptAll,
  onPreviewFull,
  onAccepted,
}: ResultSidebarProps) {
  const [busy, setBusy] = useState<'accept' | 'preview' | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accepted, setAccepted] = useState(false);

  const handlePreview = async () => {
    setBusy('preview');
    setError(null);
    try {
      const path = await onPreviewFull();
      setPreviewPath(path);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const handleAccept = async () => {
    setBusy('accept');
    setError(null);
    try {
      await onAcceptAll();
      setAccepted(true);
      onAccepted();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-3.5 sticky top-4">
      <div className="bg-gradient-to-br from-[#1b2331] to-[#14171c] border border-signal/25 rounded-xl p-4">
        <div className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
          Result if you accept
        </div>
        <div className="mt-3">
          <div className={`font-mono text-2xl font-semibold ${enabledCount > 0 ? 'text-confirm' : 'text-text'}`}>
            {enabledCount}/{totalCount}
          </div>
          <div className="font-mono text-[10.5px] text-text/40 mt-0.5">fixes on</div>
        </div>

        <div className="mt-4 pt-3.5 border-t border-white/9 flex flex-col gap-2">
          <button
            onClick={handleAccept}
            disabled={busy != null || enabledCount === 0}
            className="font-semibold text-sm text-canvas bg-signal rounded-lg py-3 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy === 'accept' ? 'Saving…' : 'Accept all & save version'}
          </button>
          <button
            onClick={handlePreview}
            disabled={busy != null || enabledCount === 0}
            className="font-semibold text-xs text-text/70 border border-white/14 rounded-lg py-2.5 disabled:opacity-50"
          >
            {busy === 'preview' ? 'Rendering…' : 'Preview full mix first'}
          </button>
          <p className="text-center text-[10.5px] text-text/35">
            Saves as a new version. The original is never touched.
          </p>
        </div>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {previewPath && (
        <div className="bg-raised border border-white/8 rounded-xl p-3.5">
          <p className="font-mono text-[10.5px] text-text/40 mb-2">FULL MIX PREVIEW</p>
          <audio
            controls
            autoPlay
            preload="none"
            src={`/api/produce/clean/preview?path=${encodeURIComponent(previewPath)}`}
            className="w-full h-9"
          />
        </div>
      )}

      {accepted && (
        <div className="bg-confirm/10 border border-confirm/30 rounded-xl p-3.5">
          <p className="text-sm text-confirm font-semibold">Saved as a new version.</p>
          <p className="text-xs text-text/50 mt-1">Find it under the Versions tab.</p>
        </div>
      )}
    </div>
  );
}
