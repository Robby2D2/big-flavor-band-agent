'use client';

interface VersionOption {
  id: number;
  name: string;
  is_published: boolean;
}

interface VersionBarProps {
  versions: VersionOption[];
  sourceVersionId: number | null;
  onChangeSource: (id: number) => void;
  onStartAnalysis: () => void;
  onManageVersions: () => void;
  analyzing: boolean;
  analysisNote: string | null;
  /** The song already has stems, so this pass only measures them. */
  hasStems: boolean;
}

/**
 * "Working from" chip + version picker + Start analysis — the single entry
 * point into the review queue below. Replaces the old tab's plain <select>;
 * a version bar instead of a tab keeps "what am I working from" visible the
 * whole time you're reviewing fixes.
 */
export default function VersionBar({
  versions,
  sourceVersionId,
  onChangeSource,
  onStartAnalysis,
  onManageVersions,
  analyzing,
  analysisNote,
  hasStems,
}: VersionBarProps) {
  const current = versions.find((v) => v.id === sourceVersionId);

  return (
    <div className="bg-raised border border-white/8 rounded-xl p-4 flex flex-wrap items-center gap-4">
      <div className="flex-none">
        <div className="font-mono text-[10.5px] uppercase tracking-wider text-text/40">
          Working from
        </div>
        <div className="font-semibold text-text mt-0.5">{current?.name ?? '—'}</div>
      </div>

      <div className="flex gap-1.5 flex-1 min-w-[200px] overflow-x-auto">
        {versions.map((v) => {
          const active = v.id === sourceVersionId;
          return (
            <button
              key={v.id}
              onClick={() => onChangeSource(v.id)}
              className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-sm font-semibold whitespace-nowrap transition-colors ${
                active
                  ? 'bg-signal/10 border-signal/40 text-text'
                  : 'border-white/10 text-text/60 hover:bg-white/5'
              }`}
            >
              {v.name}
              {v.is_published && (
                <span className="font-mono text-[10px] text-signal">DEFAULT</span>
              )}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-3 flex-none">
        <button
          onClick={onManageVersions}
          className="text-xs font-semibold text-text/60 hover:text-text px-2.5 py-1.5 border border-white/14 rounded-lg"
        >
          Manage all {versions.length}
        </button>
        <div className="w-px h-6 bg-white/10" />
        <button
          onClick={onStartAnalysis}
          disabled={analyzing || sourceVersionId == null}
          className="px-4 py-2 bg-signal text-canvas font-semibold text-sm rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {analyzing ? 'Analyzing…' : 'Start analysis'}
        </button>
      </div>

      {analysisNote && (
        <p className="basis-full font-mono text-xs text-text/40">{analysisNote}</p>
      )}
      {/* Says which of the two jobs this press will actually do: with stems
          already on disk it never re-separates — that's Re-separate's job. */}
      {!analysisNote && (
        <p className="basis-full font-mono text-xs text-text/35">
          {hasStems
            ? 'measures the stems you already have · use Re-separate below to make new ones'
            : 'separates stems, then measures each · takes a minute or two'}
        </p>
      )}
    </div>
  );
}
