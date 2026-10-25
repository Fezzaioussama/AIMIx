import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json, makeApproval, makeRun, runStep } from './testData';
import { RUN_POLL_INTERVAL_MS, useRun } from './useRun';

/** Let pending promises settle and timers due within `ms` fire. */
async function advance(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

const waiting = makeRun({
  status: 'waiting',
  steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'running'), runStep(3, 'pending')],
  pending_approvals: [makeApproval()],
});

describe('useRun answering approvals', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('keeps polling a run that waits for you, so a new request shows up', async () => {
    const second = makeRun({
      ...waiting,
      pending_approvals: [makeApproval(), makeApproval({ id: 32, step_order: 3 })],
    });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(waiting))
      .mockResolvedValue(json(second));
    const { result } = renderHook(() => useRun(7));
    await advance();
    expect(result.current.run?.pending_approvals).toHaveLength(1);

    await advance(RUN_POLL_INTERVAL_MS);

    expect(result.current.run?.pending_approvals).toHaveLength(2);
    expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('approves a request and shows the run as it comes back', async () => {
    const going = makeRun({ status: 'running', pending_approvals: [] });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (path) =>
        json(path === API.approveToolCall(7, 31) ? going : waiting),
      );
    const { result } = renderHook(() => useRun(7));
    await advance();

    await act(() => result.current.approve(31));

    expect(fetchMock).toHaveBeenCalledWith(
      API.approveToolCall(7, 31),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.current.run?.status).toBe('running');
    expect(result.current.run?.pending_approvals).toEqual([]);
    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBe('');
  });

  it('declines a request the same way', async () => {
    const going = makeRun({ status: 'running', pending_approvals: [] });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (path) =>
        json(path === API.declineToolCall(7, 31) ? going : waiting),
      );
    const { result } = renderHook(() => useRun(7));
    await advance();

    await act(() => result.current.decline(31));

    expect(fetchMock).toHaveBeenCalledWith(
      API.declineToolCall(7, 31),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(result.current.run?.pending_approvals).toEqual([]);
  });

  it('says why an answer was refused and keeps the request on screen', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      path === API.approveToolCall(7, 31)
        ? json({ error: 'conflict', detail: 'This request has expired.' }, 409)
        : json(waiting),
    );
    const { result } = renderHook(() => useRun(7));
    await advance();

    await act(() => result.current.approve(31));

    expect(result.current.error).toBe('This request has expired.');
    expect(result.current.run?.pending_approvals).toHaveLength(1);
    expect(result.current.busy).toBe(false);
  });

  it('is busy while an answer is on its way', async () => {
    let settle: (response: Response) => void = () => undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((path) =>
      path === API.approveToolCall(7, 31)
        ? new Promise<Response>((resolve) => (settle = resolve))
        : Promise.resolve(json(waiting)),
    );
    const { result } = renderHook(() => useRun(7));
    await advance();

    let answering: Promise<void> = Promise.resolve();
    act(() => {
      answering = result.current.approve(31);
    });
    expect(result.current.busy).toBe(true);
    await act(async () => {
      settle(json(makeRun({ status: 'running' })));
      await answering;
    });

    expect(result.current.busy).toBe(false);
  });
});
