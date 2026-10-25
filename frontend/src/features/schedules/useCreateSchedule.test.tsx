import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { emptyScheduleDraft } from './scheduleDraft';
import { SCHEDULE, refusal, serve } from './testData';
import { useCreateSchedule } from './useCreateSchedule';

const draft = { ...emptyScheduleDraft('Europe/Paris'), run: { text: 'go', values: {} } };

describe('useCreateSchedule', () => {
  afterEach(() => vi.restoreAllMocks());

  it('creates the schedule from the draft and hands back what the server made', async () => {
    const calls = serve({ [`POST ${API.schedules}`]: SCHEDULE });
    const { result } = renderHook(() => useCreateSchedule(3, []));

    await act(() => result.current.create(draft));

    expect(calls[0].body).toEqual({
      pipeline_id: 3,
      frequency: 'weekly',
      time: '09:00',
      weekday: 0,
      timezone: 'Europe/Paris',
      input: 'go',
    });
    expect(result.current).toMatchObject({ busy: false, error: '', created: SCHEDULE });
  });

  it('is busy while it saves, and clears an earlier result when it starts again', async () => {
    let answer: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockImplementation(
      () => new Promise<Response>((resolve) => (answer = resolve)),
    );
    const { result } = renderHook(() => useCreateSchedule(3, []));

    let saving: Promise<void> = Promise.resolve();
    act(() => {
      saving = result.current.create(draft);
    });
    expect(result.current.busy).toBe(true);
    await act(async () => {
      answer(
        new Response(JSON.stringify(SCHEDULE), { headers: { 'Content-Type': 'application/json' } }),
      );
      await saving;
    });

    expect(result.current.busy).toBe(false);
    expect(result.current.created).toEqual(SCHEDULE);
  });

  it('says why a schedule was refused', async () => {
    serve({ [`POST ${API.schedules}`]: refusal('You can have up to 20 schedules.') });
    const { result } = renderHook(() => useCreateSchedule(3, []));

    await act(() => result.current.create(draft));

    expect(result.current).toMatchObject({
      busy: false,
      created: null,
      error: 'You can have up to 20 schedules.',
    });
  });

  it('clears a refusal when the next attempt works', async () => {
    const answers = [refusal('Unknown time zone.'), SCHEDULE];
    serve({ [`POST ${API.schedules}`]: () => answers.shift() });
    const { result } = renderHook(() => useCreateSchedule(3, []));

    await act(() => result.current.create(draft));
    expect(result.current.error).toBe('Unknown time zone.');
    await act(() => result.current.create(draft));

    expect(result.current).toMatchObject({ error: '', created: SCHEDULE });
  });

  it('does nothing for a pipeline that is not saved', async () => {
    const calls = serve({});
    const { result } = renderHook(() => useCreateSchedule(undefined, []));

    await act(() => result.current.create(draft));

    expect(calls).toEqual([]);
    expect(result.current).toMatchObject({ busy: false, error: '', created: null });
  });

  it('sends named values for a pipeline that declares inputs', async () => {
    const calls = serve({ [`POST ${API.schedules}`]: SCHEDULE });
    const inputs = [{ name: 'topic', label: 'Topic', description: '' }];
    const { result } = renderHook(() => useCreateSchedule(3, inputs));

    await act(() => result.current.create({ ...draft, run: { text: '', values: { topic: 'a' } } }));

    expect(calls[0].body).toMatchObject({ inputs: { topic: 'a' } });
    expect(calls[0].body).not.toHaveProperty('input');
  });

  it('drops the request when the screen goes away, updating nothing afterwards', async () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) => {
      signal = init?.signal as AbortSignal;
      return new Promise<Response>(() => {});
    });
    const { result, unmount } = renderHook(() => useCreateSchedule(3, []));
    act(() => void result.current.create(draft));

    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
