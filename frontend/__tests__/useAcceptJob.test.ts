import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAcceptJob } from '@/hooks/useAcceptJob';

const respond = (body: unknown, ok = true) =>
  ({ ok, json: async () => body }) as Response;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useAcceptJob', () => {
  it('reports which version a finished save produced, so it can be selected', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).includes('dismiss')
          ? respond({})
          : respond({
              status: 'complete',
              preview: false,
              version: { version_id: 77, is_published: false },
            })
      )
    );

    const onSaved = vi.fn();
    renderHook(() => useAcceptJob(880, onSaved));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(77));
  });

  it('reports null rather than throwing when a save carries no version', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).includes('dismiss')
          ? respond({})
          : respond({ status: 'complete', preview: false })
      )
    );

    const onSaved = vi.fn();
    renderHook(() => useAcceptJob(880, onSaved));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(null));
  });

  it('does not report a finished preview — a preview makes no version', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        respond({ status: 'complete', preview: true, candidate_path: '/tmp/mix.wav' })
      )
    );

    const onSaved = vi.fn();
    const { result } = renderHook(() => useAcceptJob(880, onSaved));

    await waitFor(() => expect(result.current.job.status).toBe('complete'));
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('does not report while a render is still running', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => respond({ status: 'running', preview: false })));

    const onSaved = vi.fn();
    const { result } = renderHook(() => useAcceptJob(880, onSaved));

    await waitFor(() => expect(result.current.job.status).toBe('running'));
    expect(onSaved).not.toHaveBeenCalled();
  });
});
