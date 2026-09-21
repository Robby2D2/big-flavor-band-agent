'use client';

import { useState, useEffect, use } from 'react';
import Link from 'next/link';
import Header from '@/components/Header';
import AudioProcessingTab from '@/components/produce/audio/AudioProcessingTab';
import FixNoticePanel from '@/components/produce/audio/FixNoticePanel';
import type { VersionDetail } from '@/components/produce/audio/VersionDetails';
import {
  formatBytes,
  formatDuration,
  formatProducedAt,
  formatSteps,
} from '@/lib/formatVersion';
import { describeAcceptJob, useAcceptJob } from '@/hooks/useAcceptJob';
import {
  UNSAVED_VERSION_ID,
  unsavedRenderFrom,
  unsavedRenderLabel,
} from '@/lib/unsavedRender';

interface CatalogSong {
  id: number;
  title: string;
}

export default function ProduceSongPage({
  params,
}: {
  params: Promise<{ songId: string }>;
}) {
  const { songId: songIdParam } = use(params);
  const songId = Number(songIdParam);

  const [song, setSong] = useState<CatalogSong | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [versions, setVersions] = useState<VersionDetail[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionBusyId, setVersionBusyId] = useState<number | null>(null);
  // Which version the details panel acts on. Lives here, not in
  // AudioProcessingTab, because the list that sets it is rendered here.
  const [selectedVersionId, setSelectedVersionId] = useState<number | null>(null);

  // Keep a valid selection: default to whatever is published, and fall back
  // when the selected version is renamed away or deleted.
  useEffect(() => {
    setSelectedVersionId((prev) => {
      if (prev === UNSAVED_VERSION_ID) return prev;
      if (prev != null && versions.some((v) => v.id === prev)) return prev;
      const published = versions.find((v) => v.is_published);
      return published?.id ?? versions[0]?.id ?? null;
    });
  }, [versions]);

  useEffect(() => {
    if (Number.isNaN(songId)) {
      setError('Invalid song id.');
      setLoading(false);
      return;
    }
    loadSong();
    loadVersions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [songId]);

  const loadSong = async () => {
    try {
      const response = await fetch(`/api/produce/songs/${songId}`);
      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        setLoading(false);
        return;
      }
      if (!response.ok) {
        throw new Error('Failed to load song');
      }
      const data = await response.json();
      setSong(data.song);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadVersions = async () => {
    setVersionsLoading(true);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/songs/${songId}/versions`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Failed to load versions');
      }
      const list: VersionDetail[] = data.versions || [];
      setVersions(list);
    } catch (err: any) {
      setVersionsError(err.message);
      setVersions([]);
    } finally {
      setVersionsLoading(false);
    }
  };

  // A background render adds a version when it lands, so the list reloads
  // itself rather than waiting for the producer to press Refresh.
  // A finished save is the version you now want to be working from, and the
  // fixes on screen were measured against the one you started from. Reload the
  // list first so the new version exists, then select it — selecting before it
  // is in `versions` would be undone by the guard below.
  const handleVersionSaved = async (versionId: number | null) => {
    await loadVersions();
    if (versionId != null) {
      setSelectedVersionId(versionId);
    }
  };

  const { job: renderJob, saveNotices, refresh: refreshRenderJob } = useAcceptJob(
    songId,
    handleVersionSaved
  );
  const renderNotice = describeAcceptJob(renderJob);
  const renderInProgress = renderJob.status === 'running';
  // Start analysis renders what it detected, so there is usually a finished mix
  // that belongs to no version yet. It keeps a row so it can be played against
  // the original before anyone decides to save it.
  const unsavedRender = unsavedRenderFrom(renderJob);

  // Intensity is only recorded by the older auto-clean path; the per-fix flow
  // has no such setting, so for most songs the column is dead space.
  const showIntensity = versions.some((v) => v.aggressiveness);

  // If the unsaved mix goes away (dismissed, or superseded by a new render)
  // while it was selected, fall back to a real version.
  useEffect(() => {
    if (!unsavedRender && selectedVersionId === UNSAVED_VERSION_ID) {
      const published = versions.find((v) => v.is_published);
      setSelectedVersionId(published?.id ?? versions[0]?.id ?? null);
    }
  }, [unsavedRender, selectedVersionId, versions]);

  const handleSetDefault = async (versionId: number) => {
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}/default`, {
        method: 'POST',
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to set default');
      }
      await loadVersions();
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleRenameVersion = async (versionId: number, currentName: string) => {
    const next = window.prompt('Rename version', currentName);
    if (next == null) return;
    const name = next.trim();
    if (!name || name === currentName) return;
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to rename');
      }
      await loadVersions();
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  const handleDeleteVersion = async (versionId: number, name: string) => {
    if (!window.confirm(`Delete version "${name}"? This removes its audio file.`)) {
      return;
    }
    setVersionBusyId(versionId);
    setVersionsError(null);
    try {
      const response = await fetch(`/api/produce/versions/${versionId}`, {
        method: 'DELETE',
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || data.error || 'Failed to delete');
      }
      await loadVersions();
    } catch (err: any) {
      setVersionsError(err.message);
    } finally {
      setVersionBusyId(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-text/55">Loading song...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-canvas flex items-center justify-center">
        <div className="max-w-md w-full bg-panel rounded-lg shadow-lg p-8">
          <div className="text-red-600 dark:text-red-400 text-center">
            <h2 className="text-2xl font-bold mb-2">Unable to load song</h2>
            <p className="text-text/55">{error}</p>
            <Link
              href="/produce"
              className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Back to catalog
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-canvas">
      <Header title="Produce" subtitle={song?.title ?? 'Song detail'} />

      <main className="container mx-auto px-4 py-8">
        <Link
          href="/produce"
          className="inline-block mb-4 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          ← Back to catalog
        </Link>

        <h1 className="text-2xl font-bold text-text mb-6">
          {song?.title}
        </h1>

        <div className="bg-panel border border-white/8 rounded-xl p-6">
          <h2 className="text-xl font-semibold text-text mb-1">Audio processing</h2>
          <p className="text-sm text-text/50 mb-4">
            Pick a starting version, then Start analysis — it separates{' '}
            <em>that version</em> into stems the first time and measures each one on
            its own; after that it reuses the stems you have for it (Re-separate
            makes new ones). Stems belong to the version they came from, so
            switching version shows that version&apos;s stems, not the song&apos;s.
            Review the detected fixes below, adjust or skip what you don&apos;t
            want, then accept the rest as a new version. The version you start
            from is never overwritten.
          </p>
          <section className="mb-8 pb-8 border-b border-white/8">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-base font-semibold text-text">Versions</h3>
              <button
                onClick={loadVersions}
                disabled={versionsLoading}
                className="text-sm px-3 py-1 border border-white/14 rounded-lg text-text/70 hover:bg-white/5 disabled:opacity-50"
              >
                {versionsLoading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            <p className="text-sm text-text/55 mb-4">
              Pick a version to work with — auditioning, renaming, deleting and
              analysing it all happen below. The default version is what plays
              everywhere: radio, search and preview, and downloads.
            </p>

            {versionsError && (
              <div className="p-3 mb-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
                {versionsError}
              </div>
            )}

            {versions.length === 0 && !versionsLoading ? (
              <p className="text-text/45 text-sm">
                No versions yet for this song.
              </p>
            ) : (
              <div className="overflow-auto border border-white/8 rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-well text-left text-text/45">
                  <tr>
                    <th className="py-2 px-3 w-8">
                      <span className="sr-only">Selected</span>
                    </th>
                    <th className="py-2 px-3">Version</th>
                    <th className="py-2 px-3">Steps</th>
                    {showIntensity && <th className="py-2 px-3">Intensity</th>}
                    <th className="py-2 px-3">Duration</th>
                    <th className="py-2 px-3">Size</th>
                    <th className="py-2 px-3">Produced</th>
                  </tr>
                </thead>
                <tbody className="text-text">
                  {renderNotice && (
                    <tr className="border-t border-white/8 bg-white/5">
                      <td className="py-2 px-3">
                        {renderNotice.tone === 'progress' ? (
                          <span className="inline-block h-3 w-3 rounded-full border-2 border-signal border-t-transparent animate-spin" />
                        ) : (
                          <span className="text-red-500">!</span>
                        )}
                      </td>
                      <td className="py-2 px-3" colSpan={showIntensity ? 6 : 5}>
                        <span
                          className={`font-medium ${
                            renderNotice.tone === 'error'
                              ? 'text-red-600 dark:text-red-400'
                              : 'text-text'
                          }`}
                        >
                          {renderNotice.label}
                        </span>
                        <span className="text-text/45 ml-2">{renderNotice.detail}</span>
                      </td>
                    </tr>
                  )}
                  {unsavedRender && (
                    <tr
                      onClick={() => setSelectedVersionId(UNSAVED_VERSION_ID)}
                      aria-selected={selectedVersionId === UNSAVED_VERSION_ID}
                      className={`border-t border-white/8 align-middle cursor-pointer ${
                        selectedVersionId === UNSAVED_VERSION_ID
                          ? 'bg-signal/10'
                          : 'hover:bg-white/5'
                      }`}
                    >
                      <td className="py-2 px-3">
                        <input
                          type="radio"
                          name="selected-version"
                          checked={selectedVersionId === UNSAVED_VERSION_ID}
                          onChange={() => setSelectedVersionId(UNSAVED_VERSION_ID)}
                          aria-label="Audition the new unsaved mix"
                          className="accent-signal"
                        />
                      </td>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">New mix</span>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200">
                            Not saved
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-text/55" colSpan={showIntensity ? 5 : 4}>
                        {unsavedRenderLabel(unsavedRender)}
                      </td>
                    </tr>
                  )}
                  {versions.map((v) => {
                    const selected = v.id === selectedVersionId;
                    return (
                      <tr
                        key={v.id}
                        onClick={() => setSelectedVersionId(v.id)}
                        aria-selected={selected}
                        className={`border-t border-white/8 align-middle cursor-pointer ${
                          selected ? 'bg-signal/10' : 'hover:bg-white/5'
                        }`}
                      >
                        <td className="py-2 px-3">
                          <input
                            type="radio"
                            name="selected-version"
                            checked={selected}
                            onChange={() => setSelectedVersionId(v.id)}
                            aria-label={`Work with ${v.name}`}
                            className="accent-signal"
                          />
                        </td>
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{v.name}</span>
                            {v.is_published && (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200">
                                Default
                              </span>
                            )}
                            {v.label === 'original' && (
                              <span className="text-xs text-text/35">original</span>
                            )}
                          </div>
                        </td>
                        <td className="py-2 px-3 text-text/55">
                          {formatSteps(v.steps_applied)}
                        </td>
                        {showIntensity && (
                          <td className="py-2 px-3 text-text/55 capitalize">
                            {v.aggressiveness ?? '—'}
                          </td>
                        )}
                        <td className="py-2 px-3 text-text/55">
                          {formatDuration(v.duration_seconds)}
                        </td>
                        <td className="py-2 px-3 text-text/55">
                          {formatBytes(v.file_size_bytes)}
                        </td>
                        <td className="py-2 px-3 text-text/55">
                          {formatProducedAt(v.created_at)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* A save's render finishes after the review queue that started it has
              been cleared for the new version, so this is where it gets to
              report a fix that did less than its card said (issue #91). */}
          {saveNotices.length > 0 && (
            <div className="mt-4">
              <FixNoticePanel notices={saveNotices} />
            </div>
          )}
          </section>

          <AudioProcessingTab
            songId={songId}
            versions={versions}
            sourceVersionId={selectedVersionId}
            onApplied={loadVersions}
            onRenderStarted={refreshRenderJob}
            renderInProgress={renderInProgress}
            unsavedRender={
              selectedVersionId === UNSAVED_VERSION_ID ? unsavedRender : null
            }
            versionActions={{
              busyId: versionBusyId,
              onSetDefault: handleSetDefault,
              onRename: handleRenameVersion,
              onDelete: handleDeleteVersion,
            }}
          />
        </div>
      </main>
    </div>
  );
}
