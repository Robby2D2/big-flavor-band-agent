'use client';

import LyricsPanel from '../LyricsPanel';

interface LyricsCardProps {
  songId: number;
}

/**
 * Lyrics folded into the audio-processing sidebar instead of a separate top
 * -level tab — reuses LyricsPanel's fetch/save/re-extract logic unchanged;
 * only the surrounding card frame is new. LyricsPanel's own `dark:` classes
 * already render correctly under the app-wide dark theme (Phase A); a full
 * pass onto the Console color tokens happens with the rest of the app later.
 */
export default function LyricsCard({ songId }: LyricsCardProps) {
  return (
    <div className="bg-raised border border-white/8 rounded-xl p-4">
      <h3 className="font-semibold text-text mb-3">Lyrics</h3>
      <LyricsPanel songId={songId} />
    </div>
  );
}
