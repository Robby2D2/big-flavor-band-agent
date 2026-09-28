'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';

import Header from '@/components/Header';
import TakeCard, {
  SessionTake,
} from '@/components/produce/session/TakeCard';
import TakeGroupCard from '@/components/produce/session/TakeGroupCard';
import { stemColor } from '@/components/produce/audio/stemColors';
import { TakeGroupRecord, reviewRows } from '@/lib/takeGroups';

interface SessionTrack {
  id: number;
  name: string;
  role: string;
  rec_pass: number | null;
  position_seconds: number | null;
  peak_db: number | null;
  is_dead: boolean;
}

interface SessionDetail {
  id: number;
  name: string;
  recorded_on: string | null;
  status: string;
  stage: string | null;
  progress: number;
  error: string | null;
  rec_passes: number[];
  sample_rate: number | null;
  duration_seconds: number | null;
  tracks: SessionTrack[];
  takes: SessionTake[];
  groups: TakeGroupRecord[];
}

const STAGE_COPY: Record<string, string> = {
  downloading: 'Downloading the session from Google Drive',
  unpacking: 'Unpacking the upload',
  scanning: 'Measuring every channel',
  transcribing: 'Listening for where the songs are',
  rendering: 'Cutting the takes and their channels',
};

export default function SessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = String(params.sessionId);

  const [session, setSession] = useState<SessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showDead, setShowDead] = useState(false);
  const [regrouping, setRegrouping] = useState(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`/api/produce/sessions/${sessionId}`);
      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        return;
      }
      if (response.status === 404) {
        setError('That session no longer exists.');
        return;
      }
      if (!response.ok) throw new Error('Failed to load the session');
      setSession(await response.json());
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load the session');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    load();
  }, [load]);

  const busy = session?.status === 'running' || session?.status === 'queued';

  // Follow the scan while it runs, and stop the moment it lands — a reload
  // mid-scan picks the story back up because the stage lives in the database.
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [busy, load]);

  const toggleExcluded = async (take: SessionTake) => {
    // Optimistic: the only failure mode is the flag not sticking, and the next
    // poll or reload corrects it.
    setSession((current) =>
      current
        ? {
            ...current,
            takes: current.takes.map((row) =>
              row.id === take.id ? { ...row, excluded: !row.excluded } : row
            ),
          }
        : current
    );
    await fetch(`/api/produce/sessions/takes/${take.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ excluded: !take.excluded }),
    }).catch(() => load());
  };

  const renameGroup = async (group: TakeGroupRecord, name: string) => {
    await fetch(`/api/produce/sessions/groups/${group.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    });
    load();
  };

  // Clicking the chosen keeper again clears it: the producer must be able to go
  // back to "not decided yet", which is where every group starts (SESS-15).
  const chooseKeeper = async (group: TakeGroupRecord, take: SessionTake) => {
    const keeper = group.keeper_take_id === take.id ? null : take.id;
    await fetch(`/api/produce/sessions/groups/${group.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keeper_take_id: keeper }),
    });
    load();
  };

  const separate = async (take: SessionTake) => {
    await fetch(`/api/produce/sessions/takes/${take.id}/separate`, {
      method: 'POST',
    });
    load();
  };

  const regroup = async () => {
    if (
      !window.confirm(
        'Guess the songs again from what was transcribed? Any group name you set and any keeper you chose will be discarded. No take or audio is lost.'
      )
    ) {
      return;
    }
    setRegrouping(true);
    await fetch(`/api/produce/sessions/${sessionId}/regroup`, { method: 'POST' })
      .catch(() => undefined)
      .finally(() => setRegrouping(false));
    load();
  };

  const remove = async () => {
    if (!window.confirm('Delete this session and everything rendered from it?')) {
      return;
    }
    await fetch(`/api/produce/sessions/${sessionId}`, { method: 'DELETE' });
    router.push('/produce/sessions');
  };

  const liveTracks = useMemo(
    () => (session?.tracks ?? []).filter((track) => !track.is_dead),
    [session]
  );
  const deadTracks = useMemo(
    () => (session?.tracks ?? []).filter((track) => track.is_dead),
    [session]
  );

  const kept = (session?.takes ?? []).filter((take) => !take.excluded);

  // Grouping rearranges takes; it never removes one. Every take the scan found is
  // in exactly one row, either inside its song's group or on its own (SESS-14).
  const rows = useMemo(
    () => reviewRows(session?.takes ?? [], session?.groups ?? []),
    [session]
  );
  const groupCount = rows.filter((row) => row.kind === 'group').length;

  return (
    <div className="min-h-screen bg-canvas text-text">
      <Header
        title="Recording session"
        subtitle="Review the takes found in this rehearsal"
      />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <Link
          href="/produce/sessions"
          className="text-sm text-text/50 hover:text-text"
        >
          ← All sessions
        </Link>

        {loading && <p className="mt-6 text-sm text-text/60">Loading…</p>}
        {error && <p className="mt-6 text-sm text-attention">{error}</p>}

        {session && (
          <>
            <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
              <div>
                <h1 className="text-2xl font-semibold">{session.name}</h1>
                <p className="mt-1 text-sm text-text/60">
                  {session.recorded_on ?? 'Undated'}
                  {session.sample_rate
                    ? ` · ${(session.sample_rate / 1000).toFixed(1)} kHz`
                    : ''}
                  {session.rec_passes.length
                    ? ` · ${session.rec_passes.length} recording ${
                        session.rec_passes.length === 1 ? 'pass' : 'passes'
                      }`
                    : ''}
                  {liveTracks.length ? ` · ${liveTracks.length} channels` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={remove}
                className="rounded border border-raised px-3 py-2 text-sm text-text/70 hover:bg-raised"
              >
                Delete session
              </button>
            </div>

            {busy && (
              <div className="mt-6 rounded border border-signal/40 bg-signal/5 p-4">
                <div className="flex justify-between text-sm">
                  <span>{STAGE_COPY[session.stage ?? ''] ?? 'Working'}</span>
                  <span className="font-mono text-text/60">
                    {session.progress}%
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded bg-well">
                  <div
                    className="h-full bg-signal transition-[width] duration-500"
                    style={{ width: `${session.progress}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-text/50">
                  This takes a while — a session is hours of multitrack audio.
                  You can leave this page and come back.
                </p>
              </div>
            )}

            {session.status === 'failed' && (
              <div className="mt-6 rounded border border-attention/40 bg-attention/10 p-4">
                <p className="text-sm font-medium text-attention">
                  The scan failed.
                </p>
                <p className="mt-1 font-mono text-xs text-attention/80">
                  {session.error}
                </p>
              </div>
            )}

            {session.status === 'uploading' && (
              <p className="mt-6 rounded border border-raised bg-panel p-4 text-sm text-text/60">
                This session&apos;s upload never finished, so there is nothing to scan.
              </p>
            )}

            {session.takes.length > 0 && (
              <section className="mt-8">
                <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
                  <h2 className="text-lg font-medium">
                    {session.takes.length}{' '}
                    {session.takes.length === 1 ? 'take' : 'takes'}
                    {groupCount > 0 && (
                      <span className="ml-2 text-sm font-normal text-text/50">
                        in {groupCount} {groupCount === 1 ? 'song' : 'songs'} and{' '}
                        {rows.length - groupCount} on their own
                      </span>
                    )}
                  </h2>
                  <div className="flex items-baseline gap-3">
                    <p className="text-xs text-text/40">
                      Open one to hear it and see its channels
                    </p>
                    {!busy && (
                      <button
                        type="button"
                        onClick={regroup}
                        disabled={regrouping}
                        className="rounded border border-raised px-2 py-1 text-xs text-text/70 hover:bg-raised disabled:opacity-50"
                      >
                        {regrouping ? 'Guessing…' : 'Re-guess songs'}
                      </button>
                    )}
                  </div>
                </div>
                <ul className="space-y-2">
                  {rows.map((row) =>
                    row.kind === 'group' ? (
                      <TakeGroupCard
                        key={`group-${row.group.id}`}
                        group={row.group}
                        takes={row.takes}
                        onRename={renameGroup}
                        onChooseKeeper={chooseKeeper}
                        onSeparate={separate}
                        onToggleExcluded={toggleExcluded}
                      />
                    ) : (
                      <TakeCard
                        key={row.take.id}
                        take={row.take}
                        index={row.position}
                        onToggleExcluded={toggleExcluded}
                      />
                    )
                  )}
                </ul>
                <p className="mt-3 text-xs text-text/40">
                  Detection is a first pass — a stretch of talking can read as a
                  song, and which takes are the same song is guessed from the words
                  they share, not matched against the catalog. A take that fits no
                  song stands on its own. Discard anything that isn&apos;t a song;
                  nothing is imported into the catalog until you say so.
                  {kept.length !== session.takes.length &&
                    ` ${session.takes.length - kept.length} discarded so far.`}
                </p>
              </section>
            )}

            {session.status === 'complete' && session.takes.length === 0 && (
              <p className="mt-8 rounded border border-raised bg-panel p-6 text-sm text-text/60">
                The scan finished but found nothing that looked like a song.
              </p>
            )}

            {session.tracks.length > 0 && (
              <section className="mt-10">
                <h2 className="mb-3 text-lg font-medium">Channels</h2>
                <ul className="space-y-1">
                  {liveTracks.map((track) => (
                    <li
                      key={track.id}
                      className="flex flex-wrap items-center gap-3 rounded bg-panel px-3 py-2 text-sm"
                    >
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: stemColor(track.role) }}
                      />
                      <span className="flex-1">{track.name}</span>
                      <span className="text-xs text-text/40">{track.role}</span>
                      {track.peak_db !== null && (
                        <span className="font-mono text-xs text-text/40">
                          {track.peak_db.toFixed(1)} dB
                        </span>
                      )}
                      {track.rec_pass !== null && (
                        <span className="font-mono text-xs text-text/30">
                          pass {track.rec_pass}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>

                {deadTracks.length > 0 && (
                  <>
                    <button
                      type="button"
                      onClick={() => setShowDead((value) => !value)}
                      className="mt-3 text-xs text-text/40 hover:text-text/70"
                    >
                      {showDead ? 'Hide' : 'Show'} {deadTracks.length} empty{' '}
                      {deadTracks.length === 1 ? 'channel' : 'channels'}
                    </button>
                    {showDead && (
                      <ul className="mt-2 space-y-1">
                        {deadTracks.map((track) => (
                          <li
                            key={track.id}
                            className="flex items-center gap-3 rounded bg-well px-3 py-1.5 text-xs text-text/40"
                          >
                            <span className="flex-1">{track.name}</span>
                            <span>no audio</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </section>
            )}
          </>
        )}
      </main>
    </div>
  );
}
