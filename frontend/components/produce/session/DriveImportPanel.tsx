'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';

/** One Reaper project folder on the band's Drive, as the backend lists it. */
export interface DriveFolder {
  id: string;
  folder_name: string;
  /** The folders it is filed inside, when it is not at the top level. */
  location: string | null;
  name: string;
  recorded_on: string | null;
  /** The session this folder was imported as, or null if it never was. */
  session_id: number | null;
  session_status: string | null;
}

interface DriveImportPanelProps {
  folders: DriveFolder[] | null;
  error: string | null;
  /** The folder whose import is being started, so its button can say so. */
  importingId: string | null;
  onImport: (folder: DriveFolder) => void;
  onClose: () => void;
}

const importedLabel = (status: string | null): string => {
  if (status === 'complete') return 'Imported';
  if (status === 'failed') return 'Import failed';
  return 'Importing';
};

/**
 * Pick a session folder from Google Drive to import.
 *
 * The download happens on the server, so nothing passes through the browser
 * and the tab can be closed once the import has started.
 */
export default function DriveImportPanel({
  folders,
  error,
  importingId,
  onImport,
  onClose,
}: DriveImportPanelProps) {
  const [filter, setFilter] = useState('');

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (!folders || !needle) return folders ?? [];
    return folders.filter((folder) => folder.folder_name.toLowerCase().includes(needle));
  }, [folders, filter]);

  return (
    <div className="mb-6 rounded border border-raised bg-panel p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-medium">Import from Google Drive</h2>
          <p className="text-xs text-text/50">
            Downloaded on the server — no zip, and you can leave this page once it
            starts.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-raised px-3 py-1 text-sm hover:bg-raised"
        >
          Close
        </button>
      </div>

      {error && (
        <p className="rounded border border-attention/40 bg-attention/10 p-3 text-sm text-attention">
          {error}
        </p>
      )}

      {!error && folders === null && (
        <p className="text-sm text-text/60">Reading the Drive folder…</p>
      )}

      {folders && folders.length === 0 && (
        <p className="text-sm text-text/60">No session folders found on Drive.</p>
      )}

      {folders && folders.length > 0 && (
        <>
          <input
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by name or date"
            aria-label="Filter Drive folders"
            className="mb-3 w-full rounded border border-raised bg-well px-3 py-2 text-sm"
          />
          <ul className="max-h-96 divide-y divide-raised overflow-y-auto">
            {shown.map((folder) => (
              <li
                key={folder.id}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
              >
                <div className="min-w-0">
                  <span className="block truncate text-sm">{folder.name}</span>
                  <span className="font-mono text-xs text-text/50">
                    {folder.recorded_on ?? folder.folder_name}
                  </span>
                  {folder.location && (
                    <span className="ml-2 text-xs text-text/40">
                      in {folder.location}
                    </span>
                  )}
                </div>
                {folder.session_id ? (
                  <Link
                    href={`/produce/sessions/${folder.session_id}`}
                    className="rounded border border-raised px-3 py-1 text-sm hover:bg-raised"
                  >
                    {importedLabel(folder.session_status)} · Open
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => onImport(folder)}
                    disabled={importingId !== null}
                    className="rounded bg-signal px-3 py-1 text-sm font-medium text-canvas disabled:opacity-50"
                  >
                    {importingId === folder.id ? 'Starting…' : 'Import'}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
