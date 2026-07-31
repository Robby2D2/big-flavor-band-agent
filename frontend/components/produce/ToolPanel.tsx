'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

// ---------------------------------------------------------------------------
// Per-tool audio editor (issue: per-tool audio API).
//
// Drives the registry-backed /api/produce/tools* endpoints: lists every
// applicable tool with its declared, adjustable params, lets the producer tweak
// them, run that ONE tool's Analyze to see what it found, optionally adopt the
// recommended values, then Apply — which saves an auditionable candidate
// version (surfaced in the page's version list via onApplied).
// ---------------------------------------------------------------------------

interface ParamMeta {
  name: string;
  type: 'number' | 'integer' | 'boolean' | 'string' | 'array' | 'object';
  default: any;
  min: number | null;
  max: number | null;
  label: string;
  help: string | null;
  required: boolean;
  choices: any[] | null;
}

interface ToolInfo {
  name: string;
  summary: string;
  description: string;
  applies_to_file: boolean;
  hidden_from_editor: boolean;
  params: ParamMeta[];
}

interface AnalysisResult {
  recommended: boolean;
  params: Record<string, any>;
  findings: Record<string, any>;
  reason?: string;
  message?: string;
}

interface VersionOption {
  id: number;
  name: string;
  is_published: boolean;
}

interface ToolPanelProps {
  songId: number;
  versions: VersionOption[];
  onApplied: () => void;
}

// Standard params the panel manages itself (source file, output, region) — not
// rendered as per-tool controls. `strength` (wet/dry) IS a meaningful knob, so
// it stays.
const HIDDEN_PARAMS = new Set(['file_path', 'output_path', 'start_s', 'end_s']);

type ParamValues = Record<string, Record<string, any>>;

export default function ToolPanel({ songId, versions, onApplied }: ToolPanelProps) {
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [sourceVersionId, setSourceVersionId] = useState<number | ''>('');
  const [startS, setStartS] = useState('');
  const [endS, setEndS] = useState('');

  const [values, setValues] = useState<ParamValues>({});
  const [analysis, setAnalysis] = useState<Record<string, AnalysisResult>>({});
  const [busy, setBusy] = useState<Record<string, 'analyze' | 'apply' | null>>({});
  const [messages, setMessages] = useState<Record<string, { kind: 'ok' | 'err'; text: string } | null>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadTools();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadTools = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetch('/api/produce/tools');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load tools');
      const editable: ToolInfo[] = (data.tools || []).filter(
        (t: ToolInfo) => t.applies_to_file && !t.hidden_from_editor
      );
      setTools(editable);
      // Seed each tool's control values from its declared defaults.
      const seed: ParamValues = {};
      for (const tool of editable) {
        seed[tool.name] = {};
        for (const p of tool.params) {
          if (HIDDEN_PARAMS.has(p.name)) continue;
          seed[tool.name][p.name] = p.default ?? (p.type === 'boolean' ? false : '');
        }
      }
      setValues(seed);
    } catch (err: any) {
      setLoadError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const region = useMemo(() => {
    const s = startS.trim() === '' ? null : Number(startS);
    const e = endS.trim() === '' ? null : Number(endS);
    return { start_s: Number.isFinite(s as number) ? s : null, end_s: Number.isFinite(e as number) ? e : null };
  }, [startS, endS]);

  const setParam = (tool: string, name: string, value: any) => {
    setValues((prev) => ({ ...prev, [tool]: { ...prev[tool], [name]: value } }));
  };

  // Turn the control state into a params payload the backend understands:
  // coerce numbers, drop empty optionals, parse JSON for array/object params.
  const buildParams = (tool: ToolInfo): Record<string, any> => {
    const out: Record<string, any> = {};
    const vals = values[tool.name] || {};
    for (const p of tool.params) {
      if (HIDDEN_PARAMS.has(p.name)) continue;
      const raw = vals[p.name];
      if (p.type === 'boolean') {
        out[p.name] = Boolean(raw);
      } else if (p.type === 'number' || p.type === 'integer') {
        if (raw === '' || raw == null) continue;
        const n = Number(raw);
        if (Number.isFinite(n)) out[p.name] = n;
      } else if (p.type === 'array' || p.type === 'object') {
        if (typeof raw === 'string') {
          if (raw.trim() === '') continue;
          try {
            out[p.name] = JSON.parse(raw);
          } catch {
            /* skip invalid JSON */
          }
        } else if (raw != null) {
          out[p.name] = raw;
        }
      } else {
        if (raw === '' || raw == null) continue;
        out[p.name] = raw;
      }
    }
    return out;
  };

  const analyzeTool = async (tool: ToolInfo) => {
    setBusy((b) => ({ ...b, [tool.name]: 'analyze' }));
    setMessages((m) => ({ ...m, [tool.name]: null }));
    try {
      const res = await fetch(`/api/produce/tools/${tool.name}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          source_version_id: sourceVersionId === '' ? null : sourceVersionId,
          start_s: region.start_s,
          end_s: region.end_s,
          params: buildParams(tool),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Analyze failed');
      setAnalysis((a) => ({ ...a, [tool.name]: data.result as AnalysisResult }));
    } catch (err: any) {
      setMessages((m) => ({ ...m, [tool.name]: { kind: 'err', text: err.message } }));
    } finally {
      setBusy((b) => ({ ...b, [tool.name]: null }));
    }
  };

  const useRecommended = (tool: ToolInfo) => {
    const rec = analysis[tool.name]?.params || {};
    setValues((prev) => {
      const next = { ...(prev[tool.name] || {}) };
      for (const [k, v] of Object.entries(rec)) {
        // Arrays/objects are edited as JSON text in the control.
        next[k] = Array.isArray(v) || (v && typeof v === 'object') ? JSON.stringify(v) : v;
      }
      return { ...prev, [tool.name]: next };
    });
  };

  const applyTool = async (tool: ToolInfo) => {
    setBusy((b) => ({ ...b, [tool.name]: 'apply' }));
    setMessages((m) => ({ ...m, [tool.name]: null }));
    try {
      const res = await fetch(`/api/produce/tools/${tool.name}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          song_id: songId,
          source_version_id: sourceVersionId === '' ? null : sourceVersionId,
          start_s: region.start_s,
          end_s: region.end_s,
          params: buildParams(tool),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Apply failed');
      setMessages((m) => ({
        ...m,
        [tool.name]: { kind: 'ok', text: 'Applied — a new candidate version was created below.' },
      }));
      onApplied();
    } catch (err: any) {
      setMessages((m) => ({ ...m, [tool.name]: { kind: 'err', text: err.message } }));
    } finally {
      setBusy((b) => ({ ...b, [tool.name]: null }));
    }
  };

  const renderControl = (tool: ToolInfo, p: ParamMeta) => {
    const val = values[tool.name]?.[p.name];
    const id = `${tool.name}-${p.name}`;
    const disabled = !!busy[tool.name];

    if (p.type === 'boolean') {
      return (
        <label htmlFor={id} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input
            id={id}
            type="checkbox"
            checked={Boolean(val)}
            disabled={disabled}
            onChange={(e) => setParam(tool.name, p.name, e.target.checked)}
          />
          {p.label}
        </label>
      );
    }

    if (p.choices && p.choices.length > 0) {
      return (
        <div>
          <label htmlFor={id} className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{p.label}</label>
          <select
            id={id}
            value={val ?? ''}
            disabled={disabled}
            onChange={(e) => setParam(tool.name, p.name, e.target.value)}
            className="w-full text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          >
            <option value="">Auto</option>
            {p.choices.map((c) => (
              <option key={String(c)} value={String(c)}>{String(c)}</option>
            ))}
          </select>
        </div>
      );
    }

    if (p.type === 'array' || p.type === 'object') {
      return (
        <div>
          <label htmlFor={id} className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
            {p.label} <span className="text-gray-400">(JSON)</span>
          </label>
          <textarea
            id={id}
            rows={2}
            value={typeof val === 'string' ? val : val ? JSON.stringify(val) : ''}
            disabled={disabled}
            placeholder={p.type === 'array' ? '[{"frequency": 200, "gain_db": -3}]' : '{}'}
            onChange={(e) => setParam(tool.name, p.name, e.target.value)}
            className="w-full text-xs font-mono rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          />
        </div>
      );
    }

    const isNum = p.type === 'number' || p.type === 'integer';
    const hasRange = isNum && p.min != null && p.max != null;
    const step = hasRange && (p.max! - p.min!) <= 2 ? 0.05 : p.type === 'integer' ? 1 : 0.1;

    return (
      <div>
        <label htmlFor={id} className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
          {p.label}
          {isNum && val !== '' && val != null && (
            <span className="ml-2 tabular-nums text-gray-700 dark:text-gray-300">{val}</span>
          )}
        </label>
        {hasRange ? (
          <input
            id={id}
            type="range"
            min={p.min!}
            max={p.max!}
            step={step}
            value={val === '' || val == null ? p.default ?? p.min! : val}
            disabled={disabled}
            onChange={(e) => setParam(tool.name, p.name, Number(e.target.value))}
            className="w-full"
          />
        ) : (
          <input
            id={id}
            type={isNum ? 'number' : 'text'}
            value={val ?? ''}
            step={isNum ? step : undefined}
            disabled={disabled}
            placeholder={p.default != null ? `default ${p.default}` : 'optional'}
            onChange={(e) => setParam(tool.name, p.name, isNum ? e.target.value : e.target.value)}
            className="w-full text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          />
        )}
        {p.help && <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">{p.help}</p>}
      </div>
    );
  };

  if (loading) {
    return <p className="text-sm text-gray-500 dark:text-gray-400">Loading tools…</p>;
  }
  if (loadError) {
    return (
      <div className="p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg text-sm">
        {loadError}
      </div>
    );
  }

  return (
    <div>
      {/* Shared controls: which version to work from + optional region. */}
      <div className="flex flex-wrap items-end gap-4 mb-4 pb-4 border-b border-gray-200 dark:border-gray-700">
        <div>
          <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Start from</label>
          <select
            value={sourceVersionId}
            onChange={(e) => setSourceVersionId(e.target.value === '' ? '' : Number(e.target.value))}
            className="text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          >
            <option value="">Original</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>{v.name}{v.is_published ? ' (default)' : ''}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Region start (s)</label>
          <input
            type="number"
            value={startS}
            placeholder="whole song"
            onChange={(e) => setStartS(e.target.value)}
            className="w-28 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Region end (s)</label>
          <input
            type="number"
            value={endS}
            placeholder="whole song"
            onChange={(e) => setEndS(e.target.value)}
            className="w-28 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2 py-1 text-gray-900 dark:text-white"
          />
        </div>
      </div>

      <div className="space-y-3">
        {tools.map((tool) => {
          const isOpen = expanded[tool.name];
          const editable = tool.params.filter((p) => !HIDDEN_PARAMS.has(p.name));
          const a = analysis[tool.name];
          const msg = messages[tool.name];
          const toolBusy = busy[tool.name];
          return (
            <div key={tool.name} className="border border-gray-200 dark:border-gray-700 rounded-lg">
              <button
                onClick={() => setExpanded((e) => ({ ...e, [tool.name]: !e[tool.name] }))}
                className="w-full flex items-center justify-between px-4 py-3 text-left"
              >
                <span>
                  <span className="font-medium text-gray-900 dark:text-white">{tool.summary || tool.name}</span>
                  <span className="ml-2 text-xs text-gray-400">{tool.name}</span>
                </span>
                <span className="text-gray-400">{isOpen ? '▾' : '▸'}</span>
              </button>

              {isOpen && (
                <div className="px-4 pb-4 space-y-4">
                  {editable.length > 0 ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {editable.map((p) => (
                        <div key={p.name}>{renderControl(tool, p)}</div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-400">No adjustable parameters.</p>
                  )}

                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => analyzeTool(tool)}
                      disabled={!!toolBusy}
                      className="text-sm px-3 py-1.5 border border-blue-300 dark:border-blue-700 rounded text-blue-700 dark:text-blue-300 hover:bg-blue-50 dark:hover:bg-blue-900/30 disabled:opacity-50"
                    >
                      {toolBusy === 'analyze' ? 'Analyzing…' : 'Analyze'}
                    </button>
                    <button
                      onClick={() => applyTool(tool)}
                      disabled={!!toolBusy}
                      className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 dark:disabled:bg-gray-600"
                    >
                      {toolBusy === 'apply' ? 'Applying…' : 'Apply'}
                    </button>
                  </div>

                  {a && (
                    <div className="rounded-lg bg-gray-50 dark:bg-gray-900 p-3 text-sm">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full ${
                            a.recommended
                              ? 'bg-amber-100 dark:bg-amber-900 text-amber-700 dark:text-amber-200'
                              : 'bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200'
                          }`}
                        >
                          {a.recommended ? 'Recommended' : 'Looks fine'}
                        </span>
                        <span className="text-gray-700 dark:text-gray-300">{a.reason || a.message}</span>
                      </div>
                      {a.params && Object.keys(a.params).length > 0 && (
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                          <span className="text-xs text-gray-500 dark:text-gray-400">Suggested:</span>
                          {Object.entries(a.params).map(([k, v]) => (
                            <span key={k} className="text-xs font-mono px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                              {k}={Array.isArray(v) || (v && typeof v === 'object') ? JSON.stringify(v) : String(v)}
                            </span>
                          ))}
                          <button
                            onClick={() => useRecommended(tool)}
                            className="text-xs px-2 py-0.5 border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                          >
                            Use recommended
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {msg && (
                    <p className={`text-sm ${msg.kind === 'ok' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                      {msg.text}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
