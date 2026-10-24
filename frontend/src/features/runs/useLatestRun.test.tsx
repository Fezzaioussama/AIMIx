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
