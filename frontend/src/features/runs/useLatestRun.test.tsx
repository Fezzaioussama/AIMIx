import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json, makeRun } from './testData';
import { useLatestRun } from './useLatestRun';

describe('useLatestRun', () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the pipeline's newest run when the pipeline opens", async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (path) =>
        String(path).startsWith(`${API.runs}?`)
          ? json({ items: [{ ...makeRun({ status: 'succeeded' }) }], total: 4 })
          : json(makeRun({ status: 'succeeded' })),
      );

    const { result } = renderHook(() => useLatestRun(3));

    await waitFor(() => expect(result.current.run?.id).toBe(7));
    expect(fetchMock.mock.calls[0][0]).toBe(`${API.runs}?limit=1&offset=0&pipeline_id=3`);
  });

  it('follows a run started here, even if the history answers later', async () => {
    let answer: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockImplementation((path) =>
      String(path).startsWith(`${API.runs}?`)
        ? new Promise<Response>((resolve) => {
            answer = resolve;
          })
        : Promise.resolve(json(makeRun({ id: 9, status: 'succeeded' }))),
    );
    const { result } = renderHook(() => useLatestRun(3));

    act(() => result.current.follow(makeRun({ id: 9, status: 'queued' })));
    expect(result.current.run?.id).toBe(9);
    await act(async () => answer(json({ items: [makeRun({ id: 2 })], total: 1 })));

    expect(result.current.run?.id).toBe(9);
  });

  it('shows nothing for a pipeline that is not saved yet', () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const { result } = renderHook(() => useLatestRun(undefined));
    expect(result.current.run).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

/** The history answers when `answer` is called; the run itself at once. */
function pendingHistory(run: () => Response = () => json(makeRun())) {
  const history: { answer: (response: Response) => void } = { answer: () => {} };
  vi.spyOn(globalThis, 'fetch').mockImplementation((path) =>
    String(path).startsWith(`${API.runs}?`)
      ? new Promise<Response>((resolve) => {
          history.answer = resolve;
        })
      : Promise.resolve(run()),
  );
  return history;
}

describe('useLatestRun: what to show is known', () => {
  afterEach(() => vi.restoreAllMocks());

  it('is checked at once for a pipeline that is not saved yet', () => {
    const { result } = renderHook(() => useLatestRun(undefined));

    expect(result.current.checked).toBe(true);
    expect(result.current.listed).toBe(false);
  });

  it('is not checked while the history has not answered', () => {
    pendingHistory();
    const { result } = renderHook(() => useLatestRun(3));

    expect(result.current.checked).toBe(false);
  });

  it('is checked once the history answers with no run', async () => {
    const history = pendingHistory();
    const { result } = renderHook(() => useLatestRun(3));

    await act(async () => history.answer(json({ items: [], total: 0 })));

    expect(result.current.checked).toBe(true);
    expect(result.current.run).toBeNull();
  });

  it('is checked when the history cannot be loaded, so the screen still settles', async () => {
    const history = pendingHistory();
    const { result } = renderHook(() => useLatestRun(3));

    await act(async () => history.answer(json({ error: 'server_error', detail: 'x' }, 500)));

    expect(result.current.checked).toBe(true);
  });

  it('is checked only once the listed run has loaded, and says it was listed', async () => {
    let answerRun: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockImplementation((path) =>
      String(path).startsWith(`${API.runs}?`)
        ? Promise.resolve(json({ items: [makeRun({ status: 'succeeded' })], total: 1 }))
        : new Promise<Response>((resolve) => {
            answerRun = resolve;
          }),
    );
    const { result } = renderHook(() => useLatestRun(3));

    await waitFor(() => expect(result.current.listed).toBe(true));
    expect(result.current.checked).toBe(false);
    await act(async () => answerRun(json(makeRun({ status: 'succeeded' }))));

    expect(result.current.run?.id).toBe(7);
    expect(result.current.checked).toBe(true);
  });

  it('is checked when the listed run cannot be loaded', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (path) =>
      String(path).startsWith(`${API.runs}?`)
        ? json({ items: [makeRun()], total: 1 })
        : json({ error: 'not_found', detail: 'Run not found.' }, 404),
    );
    const { result } = renderHook(() => useLatestRun(3));

    await waitFor(() => expect(result.current.checked).toBe(true));
    expect(result.current.run).toBeNull();
    expect(result.current.error).not.toBe('');
  });

  it('is not listed for a run started here', async () => {
    const history = pendingHistory(() => json(makeRun({ id: 9, status: 'succeeded' })));
    const { result } = renderHook(() => useLatestRun(3));

    act(() => result.current.follow(makeRun({ id: 9, status: 'queued' })));
    await act(async () => history.answer(json({ items: [makeRun({ id: 2 })], total: 1 })));

    expect(result.current.listed).toBe(false);
    expect(result.current.checked).toBe(true);
  });
});
