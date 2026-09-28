'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import Header from '@/components/Header';
import DriveImportPanel, {
  DriveFolder,
} from '@/components/produce/session/DriveImportPanel';
import {
  SessionSummary,
  UploadProgress,
  uploadSession,
} from '@/lib/sessionUpload';

interface SessionRow extends SessionSummary {
  rec_passes: number[];
  duration_seconds: number | null;
  take_count: number | null;
  created_at: string | null;
}

const STAGE_COPY: Record<string, string> = {
  downloading: 'Downloading from Drive',
  unpacking: 'Unpacking the upload',
  scanning: 'Measuring the tracks',
  transcribing: 'Listening for songs',
  rendering: 'Cutting the takes',
};

const formatDuration = (seconds: number | null): string => {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
};

/** A session is still working through the pipeline. */
const isBusy = (session: SessionRow): boolean =>
  session.status === 'running' || session.status === 'queued';

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [uploading, setUploading] = useState<UploadProgress | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Google Drive import. `driveConfigured` stays null until the backend says,
  // and false hides the option on a deployment with no Drive key.
  const [driveConfigured, setDriveConfigured] = useState<boolean | null>(null);
  const [driveOpen, setDriveOpen] = useState(false);
  const [driveFolders, setDriveFolders] = useState<DriveFolder[] | null>(null);
  const [driveError, setDriveError] = useState<string | null>(null);
  const [importingId, setImportingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await fetch('/api/produce/sessions');
      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        return;
      }
      if (!response.ok) throw new Error('Failed to load sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDrive = useCallback(async () => {
    try {
      const response = await fetch('/api/produce/sessions/drive');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Failed to read Google Drive');
      setDriveConfigured(Boolean(data.configured));
      setDriveFolders(data.folders || []);
      setDriveError(null);
    } catch (err: unknown) {
      // Configured but unreachable: keep the option so the reason can be read.
      setDriveConfigured(true);
      setDriveError(err instanceof Error ? err.message : 'Failed to read Google Drive');
    }
  }, []);

  useEffect(() => {
    load();
    loadDrive();
  }, [load, loadDrive]);

  // A scan takes tens of minutes, so the list follows it rather than making
  // someone reload to find out whether it finished.
  useEffect(() => {
    if (!sessions.some(isBusy)) return;
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, [sessions, load]);

  const onPick = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (fileInput.current) fileInput.current.value = '';

    setUploadError(null);
    setUploading({ uploaded: 0, total: file.size, percent: 0 });
    try {
      const session = await uploadSession(file, { onProgress: setUploading });
      router.push(`/produce/sessions/${session.id}`);
    } catch (err: unknown) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
      setUploading(null);
    }
  };

  const openDrive = () => {
    setDriveOpen(true);
    setDriveFolders(null);
    loadDrive();
  };

  const onImport = async (folder: DriveFolder) => {
    setImportingId(folder.id);
    setDriveError(null);
    try {
      const response = await fetch('/api/produce/sessions/drive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_id: folder.id }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Could not import from Google Drive');
      router.push(`/produce/sessions/${data.id}`);
    } catch (err: unknown) {
      setDriveError(err instanceof Error ? err.message : 'Could not import from Google Drive');
      setImportingId(null);
      loadDrive();
    }
  };

  return (
    <div className="min-h-screen bg-canvas text-text">
      <Header
        title="Recording sessions"
        subtitle="Find the songs inside a recorded rehearsal"
      />
      <main className="mx-auto max-w-5xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Recording sessions</h1>
            <p className="mt-1 text-sm text-text/60">
              Import a Reaper session from Drive or upload it, and the songs
              inside it are found for you.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/produce"
              className="rounded border border-raised px-3 py-2 text-sm hover:bg-raised"
            >
              Back to catalog
            </Link>
            {driveConfigured && (
              <button
                type="button"
                onClick={openDrive}
                disabled={!!uploading || driveOpen}
                className="rounded border border-signal/60 px-4 py-2 text-sm font-medium text-signal hover:bg-signal/10 disabled:opacity-50"
              >
                Import from Drive
              </button>
            )}
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              disabled={!!uploading}
              className="rounded bg-signal px-4 py-2 text-sm font-medium text-canvas disabled:opacity-50"
            >
              {uploading ? 'Uploading…' : 'Upload session'}
            </button>
          </div>
        </div>

        <input
          ref={fileInput}
          type="file"
          accept=".zip"
          onChange={onPick}
          className="hidden"
        />

        {driveOpen && (
          <DriveImportPanel
            folders={driveFolders}
            error={driveError}
            importingId={importingId}
            onImport={onImport}
            onClose={() => setDriveOpen(false)}
          />
        )}

        {uploading && (
          <div className="mb-6 rounded border border-raised bg-panel p-4">
            <div className="mb-2 flex justify-between text-sm">
              <span>Uploading the session zip</span>
              <span className="font-mono text-text/70">{uploading.percent}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded bg-well">
              <div
                className="h-full bg-signal transition-[width] duration-300"
                style={{ width: `${uploading.percent}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-text/50">
              Sent in pieces, so a dropped connection resumes instead of starting
              over. Keep this tab open until it finishes.
            </p>
          </div>
        )}

        {uploadError && (
          <p className="mb-6 rounded border border-attention/40 bg-attention/10 p-3 text-sm text-attention">
            {uploadError}
          </p>
        )}

        {loading && <p className="text-sm text-text/60">Loading…</p>}
        {error && <p className="text-sm text-attention">{error}</p>}

        {!loading && !error && sessions.length === 0 && (
          <div className="rounded border border-raised bg-panel p-8 text-center">
            <p className="text-text/70">No sessions yet.</p>
            <p className="mt-2 text-sm text-text/50">
              {driveConfigured
                ? 'Import a project folder from Google Drive, or upload'
                : 'Upload'}{' '}
              the zip of a Reaper project folder — the WavPack tracks and the
              .RPP together.
            </p>
          </div>
        )}

        <ul className="space-y-3">
          {sessions.map((session) => (
            <li key={session.id}>
              <Link
                href={`/produce/sessions/${session.id}`}
                className="block rounded border border-raised bg-panel p-4 hover:border-signal/60"
              >
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="font-medium">{session.name}</span>
                  <span className="font-mono text-xs text-text/50">
                    {session.recorded_on ?? ''}
                  </span>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text/60">
                  {session.status === 'complete' && (
                    <span className="text-confirm">
                      {session.take_count ?? 0} takes
                    </span>
                  )}
                  {session.status === 'failed' && (
                    <span className="text-attention">Scan failed</span>
                  )}
                  {session.status === 'uploading' && <span>Upload unfinished</span>}
                  {isBusy(session) && (
                    <span className="text-signal">
                      {STAGE_COPY[session.stage ?? ''] ?? 'Working'} · {session.progress}%
                    </span>
                  )}
                  {session.duration_seconds ? (
                    <span>{formatDuration(session.duration_seconds)} recorded</span>
                  ) : null}
                  {session.rec_passes.length > 1 && (
                    <span>{session.rec_passes.length} recording passes</span>
                  )}
                </div>

                {isBusy(session) && (
                  <div className="mt-3 h-1 overflow-hidden rounded bg-well">
                    <div
                      className="h-full bg-signal transition-[width] duration-500"
                      style={{ width: `${session.progress}%` }}
                    />
                  </div>
                )}

                {session.error && (
                  <p className="mt-2 text-xs text-attention">{session.error}</p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
