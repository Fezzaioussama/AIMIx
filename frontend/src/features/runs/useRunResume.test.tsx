import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json, makeRun, runStep, usageOf } from './testData';
import { useRun } from './useRun';

const stopped = makeRun({
  status: 'failed',
  finished_at: '2026-10-24T10:00:05Z',
  max_cost_usd: 0.5,
  usage: usageOf(2000, 800, 0.52),
  error: {
    code: 'budget_exceeded',
    detail: 'This run stopped at $0.52 because it reached its $0.50 limit.',
  },
  steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'failed'), runStep(3, 'cancelled')],
});

describe('useRun resume with a limit', () => {
  afterEach(() => vi.restoreAllMocks());

  it('sends the new limit and shows the run it comes back with', async () => {
    const resumed = makeRun({ status: 'queued', max_cost_usd: 2, usage: stopped.usage });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (path, init) =>
        init?.method === 'POST' && path === API.resumeRun(7) ? json(resumed) : json(stopped),
      );
    const { result, unmount } = renderHook(() => useRun(7));
    await waitFor(() => expect(result.current.run?.status).toBe('failed'));

    await act(async () => {
      await result.current.resume({ max_cost_usd: 2 });
    });

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(post?.[1]?.body).toBe('{"max_cost_usd":2}');
    expect(result.current.run).toMatchObject({ status: 'queued', max_cost_usd: 2 });
    expect(result.current.error).toBe('');
    unmount();
  });

  it('resumes with no body when no limit is given', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => json(makeRun({ status: 'queued' })));
    const { result, unmount } = renderHook(() => useRun(7));
    await waitFor(() => expect(result.current.run).not.toBeNull());

    await act(async () => {
      await result.current.resume();
    });

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST');
    expect(post?.[1]?.body).toBeUndefined();
    unmount();
  });

  it('shows the server refusing a limit the run has already used up', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) =>
      init?.method === 'POST'
        ? json(
            {
              error: 'budget_exceeded',
              detail:
                'This run already reached its $0.50 limit (it used $0.52). Raise the limit to resume it.',
            },
            409,
          )
        : json(stopped),
    );
    const { result, unmount } = renderHook(() => useRun(7));
    await waitFor(() => expect(result.current.run?.status).toBe('failed'));

    await act(async () => {
      await result.current.resume({ max_cost_usd: 0.5 });
    });

    expect(result.current.error).toContain('already reached its $0.50 limit');
    expect(result.current.run?.status).toBe('failed');
    expect(result.current.busy).toBe(false);
    unmount();
  });
});
