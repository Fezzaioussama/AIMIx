import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { ScheduleTiming } from '../../core/api/types';
import { json, refusal } from './testData';
import { PREVIEW_DELAY_MS, useSchedulePreview } from './useSchedulePreview';

const WEEKLY: ScheduleTiming = {
  frequency: 'weekly',
  time: '09:00',
  weekday: 0,
  timezone: 'Europe/Paris',
};

async function wait(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('useSchedulePreview', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('asks the server once the timing has stayed put, then reports the next run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => json({ next_run_at: '2026-10-26T08:00:00Z' }));
    const { result } = renderHook(() => useSchedulePreview(WEEKLY));
    expect(result.current).toEqual({ nextRunAt: null, error: '', loading: true });

    await wait(PREVIEW_DELAY_MS - 1);
    expect(fetchMock).not.toHaveBeenCalled();
    await wait(1);

    expect(result.current).toEqual({
      nextRunAt: '2026-10-26T08:00:00Z',
      error: '',
      loading: false,
    });
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.previewSchedule);
    expect(JSON.parse(String(init?.body))).toEqual(WEEKLY);
  });

  it('asks only about where the changes end up, not about each one', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => json({ next_run_at: '2026-10-26T09:30:00Z' }));
    const { result, rerender } = renderHook(({ timing }) => useSchedulePreview(timing), {
      initialProps: { timing: WEEKLY },
    });

    await wait(PREVIEW_DELAY_MS - 50);
    rerender({ timing: { ...WEEKLY, time: '10:00' } });
    await wait(PREVIEW_DELAY_MS - 50);
    rerender({ timing: { ...WEEKLY, time: '10:30' } });
    expect(result.current.loading).toBe(true);
    await wait(PREVIEW_DELAY_MS);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toMatchObject({ time: '10:30' });
    expect(result.current.nextRunAt).toBe('2026-10-26T09:30:00Z');
  });

  it('does not ask again for a new object holding the same timing', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async () => json({ next_run_at: '2026-10-26T08:00:00Z' }));
    const { rerender } = renderHook(({ timing }) => useSchedulePreview(timing), {
      initialProps: { timing: WEEKLY },
    });
    await wait(PREVIEW_DELAY_MS);

    rerender({ timing: { ...WEEKLY } });
    await wait(PREVIEW_DELAY_MS * 2);

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('cancels a request a newer timing makes obsolete, and shows only the newer answer', async () => {
    const signals: AbortSignal[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) => {
      const signal = init?.signal as AbortSignal;
      signals.push(signal);
      return new Promise<Response>((resolve) => {
        const answer = () => resolve(json({ next_run_at: `2026-10-26T0${signals.length}:00:00Z` }));
        if (signals.length === 1) setTimeout(answer, 1000);
        else answer();
      });
    });
    const { result, rerender } = renderHook(({ timing }) => useSchedulePreview(timing), {
      initialProps: { timing: WEEKLY },
    });
    await wait(PREVIEW_DELAY_MS);
    rerender({ timing: { ...WEEKLY, time: '11:00' } });
    await wait(PREVIEW_DELAY_MS);
    await wait(1500);

    expect(signals[0].aborted).toBe(true);
    expect(signals[1].aborted).toBe(false);
    expect(result.current.nextRunAt).toBe('2026-10-26T02:00:00Z');
  });

  it('asks nothing while the timing is incomplete', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const { result } = renderHook(() => useSchedulePreview(null));

    await wait(PREVIEW_DELAY_MS * 3);

    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current).toEqual({ nextRunAt: null, error: '', loading: false });
  });

  it('reports why the next run cannot be worked out', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      refusal("Unknown time zone 'Mars/Olympus'."),
    );
    const { result } = renderHook(() => useSchedulePreview(WEEKLY));

    await wait(PREVIEW_DELAY_MS);

    expect(result.current).toEqual({
      nextRunAt: null,
      error: "Unknown time zone 'Mars/Olympus'.",
      loading: false,
    });
  });

  it('drops the request when the screen goes away', async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) => {
      signal = init?.signal as AbortSignal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = renderHook(() => useSchedulePreview(WEEKLY));
    await wait(PREVIEW_DELAY_MS);

    unmount();

    expect(signal?.aborted).toBe(true);
  });

  it('does not ask at all when the screen goes away before the delay', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const { unmount } = renderHook(() => useSchedulePreview(WEEKLY));

    unmount();
    await wait(PREVIEW_DELAY_MS * 2);

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
