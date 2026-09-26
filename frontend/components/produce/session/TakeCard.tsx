'use client';

import { useEffect, useRef, useState } from 'react';

import WaveformView from '@/components/produce/WaveformView';
import { Peaks, fetchPeaks } from '@/components/produce/audioEngine';
import { stemColor } from '@/components/produce/audio/stemColors';

export interface SessionStem {
  id: number;
  name: string;
  display_name: string | null;
  peak_db: number | null;
}

export interface SessionTake {
  id: number;
  rec_pass: number | null;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  transcript: string | null;
  excluded: boolean;
  has_audio: boolean;
  stems: SessionStem[];
}

interface TakeCardProps {
  take: SessionTake;
  index: number;
  onToggleExcluded: (take: SessionTake) => void;
}

const clock = (seconds: number): string => {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  return `${minutes}:${(total % 60).toString().padStart(2, '0')}`;
};

/**
 * One detected attempt at a song: its waveform, what was sung, and the channels
 * it was played on.
 *
 * The waveform is loaded when the card is opened rather than with the list — a
 * session can hold a dozen takes and their envelopes are only needed once
 * somebody looks.
 */
export default function TakeCard({ take, index, onToggleExcluded }: TakeCardProps) {
  const [open, setOpen] = useState(false);
  const [peaks, setPeaks] = useState<Peaks | null>(null);
  const [duration, setDuration] = useState(take.duration_seconds);
  const [waveError, setWaveError] = useState<string | null>(null);
  const [playhead, setPlayhead] = useState<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!open || peaks || !take.has_audio) return;
    let cancelled = false;
    fetchPeaks(`/api/produce/sessions/takes/${take.id}/peaks`)
      .then((loaded) => {
        if (cancelled) return;
        setPeaks(loaded.peaks);
        setDuration(loaded.duration);
      })
      .catch(() => {
        if (!cancelled) setWaveError('Waveform unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [open, peaks, take.id, take.has_audio]);

  // Never leave audio playing behind a closed card.
  const toggleOpen = () => {
    setOpen((value) => {
      if (value) {
        audioRef.current?.pause();
        setPlayhead(null);
      }
      return !value;
    });
  };

  const seek = (seconds: number) => {
    setPlayhead(seconds);
    if (audioRef.current) audioRef.current.currentTime = seconds;
  };

  const played = take.stems.filter((stem) => stem.name !== 'full mix');

  return (
    <li
      className={`rounded border bg-panel ${
        take.excluded ? 'border-raised opacity-50' : 'border-raised'
      }`}
    >
      <div className="flex flex-wrap items-center gap-3 p-4">
        <button
          type="button"
          onClick={toggleOpen}
          className="flex flex-1 items-baseline gap-3 text-left"
        >
          <span className="font-mono text-xs text-text/40">{index}</span>
          <span className="font-medium">
            {take.transcript ? firstLine(take.transcript) : 'Instrumental'}
          </span>
          <span className="font-mono text-xs text-text/50">
            {clock(take.duration_seconds)}
          </span>
        </button>

        <span className="font-mono text-xs text-text/40">
          at {clock(take.start_seconds)}
          {take.rec_pass !== null ? ` · pass ${take.rec_pass}` : ''}
        </span>

        <button
          type="button"
          onClick={() => onToggleExcluded(take)}
          className="rounded border border-raised px-2 py-1 text-xs hover:bg-raised"
        >
          {take.excluded ? 'Restore' : 'Discard'}
        </button>
      </div>

      {open && (
        <div className="border-t border-raised p-4">
          {take.has_audio ? (
            <>
              <WaveformView
                peaks={peaks}
                duration={duration}
                height={80}
                playhead={playhead}
                onSeek={seek}
                waveColor={stemColor('full mix')}
              />
              {waveError && (
                <p className="mt-1 text-xs text-text/50">{waveError}</p>
              )}
              <audio
                ref={audioRef}
                controls
                preload="none"
                src={`/api/produce/sessions/takes/${take.id}/preview`}
                onTimeUpdate={(event) =>
                  setPlayhead(event.currentTarget.currentTime)
                }
                className="mt-3 w-full"
              />
            </>
          ) : (
            <p className="text-sm text-text/50">No audio was rendered for this take.</p>
          )}

          {played.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-xs uppercase tracking-wide text-text/40">
                Channels ({played.length})
              </h4>
              <ul className="flex flex-wrap gap-2">
                {played.map((stem) => (
                  <li
                    key={stem.id}
                    className="rounded bg-well px-2 py-1 text-xs"
                    style={{ color: stemColor(stem.name) }}
                    title={stem.display_name ?? stem.name}
                  >
                    {stem.display_name ?? stem.name}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-text/40">
                Already separated — the band recorded these apart, so no stem
                separation is needed.
              </p>
            </div>
          )}

          {take.transcript && (
            <div className="mt-4">
              <h4 className="mb-1 text-xs uppercase tracking-wide text-text/40">
                What was sung
              </h4>
              <p className="text-sm leading-relaxed text-text/70">
                {take.transcript}
              </p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

/** A take's headline: enough of the words to recognise the song. */
function firstLine(transcript: string): string {
  const trimmed = transcript.trim();
  return trimmed.length > 70 ? `${trimmed.slice(0, 70)}…` : trimmed;
}
