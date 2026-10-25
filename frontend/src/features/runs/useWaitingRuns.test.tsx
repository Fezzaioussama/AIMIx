import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json } from './testData';
import { useWaitingRuns, WAITING_RUNS_POLL_MS } from './useWaitingRuns';

const WAITING_URL = `${API.runs}?limit=1&offset=0&status=waiting`;

/** Let pending promises settle and timers due within `ms` fire. */
async function advance(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const page = (total: number) => json({ items: [], total });

describe('useWaitingRuns', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('is 0 until the first answer, then counts the runs that wait for you', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(page(2));
    const { result } = renderHook(() => useWaitingRuns());
    expect(result.current).toBe(0);

    await advance();

    expect(result.current).toBe(2);
    expect(fetchMock.mock.calls[0][0]).toBe(WAITING_URL);
  });

  it('asks again every few seconds, so the count follows the runs', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(page(1))
      .mockResolvedValueOnce(page(2))
      .mockResolvedValue(page(0));
    const { result } = renderHook(() => useWaitingRuns());
    await advance();
    expect(result.current).toBe(1);

    await advance(WAITING_RUNS_POLL_MS - 1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await advance(1);
    expect(result.current).toBe(2);
    await advance(WAITING_RUNS_POLL_MS);

    expect(result.current).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('keeps the last count when a fetch fails, and tries again', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(page(2))
      .mockResolvedValueOnce(json({ error: 'server_error', detail: 'Down.' }, 500))
      .mockResolvedValue(page(1));
    const { result } = renderHook(() => useWaitingRuns());
    await advance();

    await advance(WAITING_RUNS_POLL_MS);
    expect(result.current).toBe(2);
    await advance(WAITING_RUNS_POLL_MS);

    expect(result.current).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('aborts the request in flight and stops asking when it goes away', async () => {
    let signal: AbortSignal | null | undefined;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = renderHook(() => useWaitingRuns());
    await advance();

    unmount();
    await advance(WAITING_RUNS_POLL_MS * 3);

    expect(signal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not ask again after unmounting between two polls', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(page(1));
    const { unmount } = renderHook(() => useWaitingRuns());
    await advance();

    unmount();
    await advance(WAITING_RUNS_POLL_MS * 3);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
