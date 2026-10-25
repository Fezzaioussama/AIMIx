import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { makeRun } from '../runs/testData';
import { NAMED_SCHEDULE, SCHEDULE, refusal, serve } from './testData';
import { useSchedules } from './useSchedules';

async function loaded(table: Parameters<typeof serve>[0]) {
  const calls = serve({ [`GET ${API.schedules}`]: [SCHEDULE, NAMED_SCHEDULE], ...table });
  const hook = renderHook(() => useSchedules());
  await waitFor(() => expect(hook.result.current.status).toBe('idle'));
  return { calls, ...hook };
}

describe('useSchedules', () => {
  afterEach(() => vi.restoreAllMocks());

  it('loads the account’s schedules once', async () => {
    const { calls, result } = await loaded({});

    expect(result.current.schedules).toEqual([SCHEDULE, NAMED_SCHEDULE]);
    expect(result.current.notice).toBeNull();
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({ method: 'GET', path: API.schedules });
  });

  it('says when the schedules cannot be loaded', async () => {
    serve({ [`GET ${API.schedules}`]: refusal('Down.', 500, 'server_error') });
    const { result } = renderHook(() => useSchedules());

    await waitFor(() => expect(result.current.status).toBe('idle'));

    expect(result.current.schedules).toBeNull();
    expect(result.current.notice).toEqual({ kind: 'error', text: 'Down.' });
  });

  it('turns a schedule off and on, keeping the answer in the list', async () => {
    const off = { ...SCHEDULE, enabled: false, next_run_at: null };
    const { calls, result } = await loaded({
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: ({ body }: { body: { enabled: boolean } }) =>
        body.enabled ? SCHEDULE : off,
    });

    await act(() => result.current.actions.setEnabled(SCHEDULE, false));

    expect(calls[1]).toEqual({
      method: 'PATCH',
      path: API.schedule(SCHEDULE.id),
      body: { enabled: false },
    });
    expect(result.current.schedules?.[0]).toEqual(off);
    expect(result.current.schedules?.[1]).toEqual(NAMED_SCHEDULE);
    expect(result.current.notice).toEqual({
      kind: 'success',
      text: 'Schedule turned off. It will not run until you turn it on.',
    });

    await act(() => result.current.actions.setEnabled(off, true));
    expect(result.current.schedules?.[0]).toEqual(SCHEDULE);
    expect(result.current.notice?.text).toBe('Schedule turned on.');
  });

  it('saves an edit with the patch it is given', async () => {
    const edited = { ...SCHEDULE, time: '10:30' };
    const { calls, result } = await loaded({ [`PATCH ${API.schedule(SCHEDULE.id)}`]: edited });

    let saved = false;
    await act(async () => {
      saved = await result.current.actions.update(SCHEDULE, { time: '10:30' });
    });

    expect(saved).toBe(true);
    expect(calls[1].body).toEqual({ time: '10:30' });
    expect(result.current.schedules?.[0]).toEqual(edited);
    expect(result.current.notice).toEqual({ kind: 'success', text: 'Schedule saved.' });
  });

  it('reports a refused edit with the server’s words and keeps the list as it was', async () => {
    const { result } = await loaded({
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: refusal('Unknown time zone.'),
    });

    let saved = true;
    await act(async () => {
      saved = await result.current.actions.update(SCHEDULE, { timezone: 'Nowhere' });
    });

    expect(saved).toBe(false);
    expect(result.current.notice).toEqual({ kind: 'error', text: 'Unknown time zone.' });
    expect(result.current.schedules?.[0]).toEqual(SCHEDULE);
  });

  it('deletes a schedule', async () => {
    const { calls, result } = await loaded({
      [`DELETE ${API.schedule(SCHEDULE.id)}`]: () => new Response(null, { status: 204 }),
    });

    await act(() => result.current.actions.remove(SCHEDULE));

    expect(calls[1]).toMatchObject({ method: 'DELETE', path: API.schedule(SCHEDULE.id) });
    expect(result.current.schedules).toEqual([NAMED_SCHEDULE]);
    expect(result.current.notice?.text).toBe(
      'Schedule deleted. The runs it started stay in your history.',
    );
  });

  it('keeps a schedule that could not be deleted', async () => {
    const { result } = await loaded({
      [`DELETE ${API.schedule(SCHEDULE.id)}`]: refusal('Gone.', 404, 'not_found'),
    });

    await act(() => result.current.actions.remove(SCHEDULE));

    expect(result.current.schedules).toHaveLength(2);
    expect(result.current.notice).toEqual({ kind: 'error', text: 'Gone.' });
  });

  it('starts a run now and returns it', async () => {
    const run = makeRun({ id: 9, trigger: 'schedule', schedule_id: SCHEDULE.id });
    const { calls, result } = await loaded({ [`POST ${API.runSchedule(SCHEDULE.id)}`]: run });

    let started: unknown = null;
    await act(async () => {
      started = await result.current.actions.runNow(SCHEDULE);
    });

    expect(started).toEqual(run);
    expect(calls[1]).toMatchObject({ method: 'POST', path: API.runSchedule(SCHEDULE.id) });
  });

  it('returns nothing when the run could not start, and says why', async () => {
    const { result } = await loaded({
      [`POST ${API.runSchedule(SCHEDULE.id)}`]: refusal('This pipeline has no steps to run.'),
    });

    let started: unknown = 'unset';
    await act(async () => {
      started = await result.current.actions.runNow(SCHEDULE);
    });

    expect(started).toBeNull();
    expect(result.current.notice).toEqual({
      kind: 'error',
      text: 'This pipeline has no steps to run.',
    });
  });

  it('can dismiss its notice', async () => {
    const { result } = await loaded({
      [`PATCH ${API.schedule(SCHEDULE.id)}`]: SCHEDULE,
    });
    await act(() => result.current.actions.setEnabled(SCHEDULE, true));
    expect(result.current.notice).not.toBeNull();

    act(() => result.current.actions.dismiss());

    expect(result.current.notice).toBeNull();
  });

  it('cancels the load when the screen goes away', () => {
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (_path, init) => {
      signal = init?.signal as AbortSignal;
      return new Promise<Response>(() => {});
    });
    const { unmount } = renderHook(() => useSchedules());

    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
