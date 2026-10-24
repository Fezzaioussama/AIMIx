import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Run } from '../../core/api/types';
import { json, makeRun, runStep } from './testData';
import { RUN_POLL_INTERVAL_MS, useRun } from './useRun';

/** Let pending promises settle and timers due within `ms` fire. */
async function advance(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function serve(...runs: Run[]) {
  const queue = [...runs];
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async () => json(queue.shift() ?? runs.at(-1)));
}

const done = makeRun({
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
  steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'succeeded', 'b'), runStep(3, 'succeeded', 'c')],
});

describe('useRun', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('polls a running run until it finishes, then stops', async () => {
    const fetchMock = serve(makeRun(), makeRun(), done);
    const { result } = renderHook(() => useRun(7));

    await advance();
    expect(result.current.run?.status).toBe('running');
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(API.run(7));

    await advance(RUN_POLL_INTERVAL_MS - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await advance(RUN_POLL_INTERVAL_MS);
    expect(result.current.run?.status).toBe('succeeded');
    await advance(RUN_POLL_INTERVAL_MS * 5);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('fetches a finished run once and never polls it', async () => {
    const fetchMock = serve(done);
    renderHook(() => useRun(7));

    await advance(RUN_POLL_INTERVAL_MS * 4);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('aborts the request in flight and clears its timer on unmount', async () => {
    let signal: AbortSignal | null | undefined;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = renderHook(() => useRun(7));
    await advance();

    unmount();
    await advance(RUN_POLL_INTERVAL_MS * 3);

    expect(signal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('stops polling once the run is stopped', async () => {
    const stopped = makeRun({
      status: 'cancelled',
      steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'cancelled'), runStep(3, 'pending')],
    });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (path) => json(path === API.cancelRun(7) ? stopped : makeRun()));
    const { result } = renderHook(() => useRun(7));
    await advance();

    await act(() => result.current.stop());
    await advance(RUN_POLL_INTERVAL_MS * 3);

    expect(result.current.run?.status).toBe('cancelled');
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([API.run(7), API.cancelRun(7)]);
  });

  it('polls a resumed run again', async () => {
    const failed = makeRun({
      status: 'failed',
      error: { code: 'provider_timeout', detail: 'slow' },
    });
    const queued = makeRun({ status: 'queued' });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) => {
      if (path === API.resumeRun(7)) return json(queued);
      return json(fetchMock.mock.calls.length === 1 ? failed : done);
    });
    const { result } = renderHook(() => useRun(7));
    await advance(RUN_POLL_INTERVAL_MS * 2);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(() => result.current.resume());
    expect(result.current.run?.status).toBe('queued');
    await advance(RUN_POLL_INTERVAL_MS);

    expect(result.current.run?.status).toBe('succeeded');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('keeps trying after a failed fetch but gives up on a deleted run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ error: 'server_error', detail: 'Try again.' }, 500))
      .mockResolvedValueOnce(json({ error: 'not_found', detail: 'Run 7 was not found.' }, 404));
    const { result } = renderHook(() => useRun(7));
    await advance();
    expect(result.current.error).toBe('Try again.');

    await advance(RUN_POLL_INTERVAL_MS);
    expect(result.current.error).toBe('Run 7 was not found.');
    await advance(RUN_POLL_INTERVAL_MS * 3);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('shows an adopted run at once and polls it after one interval', async () => {
    const fetchMock = serve(done);
    const { result, rerender } = renderHook(({ id }) => useRun(id), {
      initialProps: { id: null as number | null },
    });
    await advance();
    expect(fetchMock).not.toHaveBeenCalled();

    act(() => result.current.adopt(makeRun({ status: 'queued' })));
    rerender({ id: 7 });
    expect(result.current.run?.status).toBe('queued');
    await advance();
    expect(fetchMock).not.toHaveBeenCalled();

    await advance(RUN_POLL_INTERVAL_MS);
    expect(result.current.run?.status).toBe('succeeded');
  });
});
