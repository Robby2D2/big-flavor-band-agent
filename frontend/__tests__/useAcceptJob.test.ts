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
  // notices ever appear is the poll that completes the job — and that poll
  // dismisses the job in the same breath. Losing them there is how a producer
  // ended up with a saved version of unchanged audio and nothing said (#91).
  const notice = {
    scope: 'drums',
    tool: 'correct_pitch',
    reason: 'Input does not look like a single line; applied a whole-file shift instead.',
  };

  it("keeps a finished save's notices after the job that carried them is dismissed", async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        String(url).includes('dismiss')
          ? respond({})
          : respond({
              status: 'complete',
              preview: false,
              version: { version_id: 77, is_published: false },
              notices: [notice],
            })
      )
    );

    const { result } = renderHook(() => useAcceptJob(880, vi.fn()));

    await waitFor(() => expect(result.current.saveNotices).toEqual([notice]));
    await waitFor(() => expect(result.current.job.status).toBe('idle'));
    expect(result.current.saveNotices).toEqual([notice]);
  });

  it('drops them when the next render starts — they describe a mix no longer on screen', async () => {
    let statusCalls = 0;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('dismiss')) return respond({});
        statusCalls += 1;
        return statusCalls === 1
          ? respond({ status: 'complete', preview: false, notices: [notice] })
          : respond({ status: 'idle' });
      })
    );

    const { result } = renderHook(() => useAcceptJob(880, vi.fn()));
    await waitFor(() => expect(result.current.saveNotices).toEqual([notice]));

    act(() => result.current.refresh());

    await waitFor(() => expect(result.current.saveNotices).toEqual([]));
  });
});
