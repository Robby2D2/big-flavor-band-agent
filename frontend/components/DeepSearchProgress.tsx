'use client';

export interface DeepSearchStep {
  kind: string;
  label: string;
  detail: string;
  at: number;
}

export interface DeepSearchJob {
  job_id: string;
  query: string;
  status: 'running' | 'complete' | 'failed';
  steps: DeepSearchStep[];
  answer: string | null;
  songs: any[];
  error: string | null;
  candidates_considered?: number;
}

/** Colour per stage, so the shape of the run is readable at a glance. */
const KIND_STYLES: Record<string, string> = {
  plan: 'text-blue-400',
  retrieve: 'text-green-400',
  evaluate: 'text-amber-400',
  refine: 'text-orange-400',
  synthesize: 'text-purple-400',
};

/**
 * What the in-depth search is doing, while it does it.
 *
 * A reasoning search that shows only a spinner asks for a minute of patience
 * and gives nothing back for it. The steps are the point: which searches it
 * chose, what it found, what it judged relevant, and when it decided the
 * evidence was thin enough to look again.
 */
export default function DeepSearchProgress({ job }: { job: DeepSearchJob }) {
  const running = job.status === 'running';

  return (
    <div className="bg-panel border border-white/8 rounded-xl p-5">
      <div className="flex items-center gap-3">
        {running && (
          <span
            role="status"
            aria-label="Working through your question"
            className="flex-none w-4 h-4 rounded-full border-2 border-blue-500 border-t-transparent animate-spin"
          />
        )}
        <h2 className="text-sm font-mono uppercase tracking-wider text-text/45">
          {running ? 'Working through your question' : 'How this was answered'}
        </h2>
      </div>

      <ol className="mt-4 space-y-1.5">
        {job.steps.map((step, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span
              className={`font-mono text-xs w-28 flex-none ${
                KIND_STYLES[step.kind] || 'text-text/45'
              }`}
            >
              {step.label}
            </span>
            <span className="text-text/60">{step.detail}</span>
          </li>
        ))}
        {running && job.steps.length === 0 && (
          <li className="text-sm text-text/45">starting…</li>
        )}
      </ol>

      {job.status === 'failed' && (
        <p className="mt-4 text-sm text-red-600 dark:text-red-400">
          {job.error || 'The search could not be completed.'}
        </p>
      )}

      {job.answer && (
        <div className="mt-5 pt-5 border-t border-white/8">
          <h3 className="text-sm font-mono uppercase tracking-wider text-text/45 mb-2">
            Answer
          </h3>
          <p className="text-text whitespace-pre-line leading-relaxed">{job.answer}</p>
          {typeof job.candidates_considered === 'number' && (
            <p className="mt-3 text-xs text-text/40">
              considered {job.candidates_considered} songs · cited {job.songs.length}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
