import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
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

  // A save answers long before its render finishes, so the only place its
  // notices ever appear is the poll that completes the job. The job now stays
  // on screen with them — the task panel reports it — while the server's copy
  // is dismissed so the same save is never reported twice (#91).
  const notice = {
    scope: 'drums',
    tool: 'correct_pitch',
    reason: 'Input does not look like a single line; applied a whole-file shift instead.',
  };

  it("keeps a finished save's notices on the job, and dismisses the server's copy", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      String(url).includes('dismiss')
        ? respond({})
        : respond({
            status: 'complete',
            preview: false,
            version: { version_id: 77, is_published: false },
            notices: [notice],
          })
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useAcceptJob(880, vi.fn()));

    await waitFor(() => expect(result.current.job.notices).toEqual([notice]));
    expect(result.current.job.status).toBe('complete');
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('dismiss'))).toBe(true);
  });

  it('cancels through the server and polls again for the outcome (PROD-19)', async () => {
    let cancelled = false;
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/cancel')) {
        cancelled = true;
        return respond({ status: 'running' });
      }
      return respond(cancelled ? { status: 'cancelled', preview: true } : { status: 'running', preview: true });
    });
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useAcceptJob(880, vi.fn()));
    await waitFor(() => expect(result.current.job.status).toBe('running'));

    await act(() => result.current.cancel());

    await waitFor(() => expect(result.current.job.status).toBe('cancelled'));
    expect(
      fetchMock.mock.calls.some(([url]) => String(url).includes('/cancel?save_only=false'))
    ).toBe(true);
  });

  it('cancels only the save when asked, and says why when it is too late', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).includes('/cancel')
          ? respond({ error: 'The version is being written and can no longer be cancelled' }, false)
          : respond({ status: 'running', preview: false })
      )
    );

    const { result } = renderHook(() => useAcceptJob(880, vi.fn()));
    await waitFor(() => expect(result.current.job.status).toBe('running'));

    await expect(result.current.cancel(true)).rejects.toThrow(/can no longer be cancelled/);
  });
});
