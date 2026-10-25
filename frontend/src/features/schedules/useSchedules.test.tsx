import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { makeRun } from '../runs/testData';
import { NAMED_SCHEDULE, SCHEDULE, refusal, serve } from './testData';
import { ACTIVE_REFRESH_MS, IDLE_REFRESH_MS, useSchedules } from './useSchedules';

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

  describe('keeping the list current', () => {
    const LIST = `GET ${API.schedules}`;
    const running = {
      ...SCHEDULE,
      last_run: { id: 12, status: 'running' as const, created_at: '2026-10-25T08:00:00Z' },
    };
    const finished = {
      ...running,
      last_run: { ...running.last_run, status: 'succeeded' as const },
    };

    async function advance(ms: number) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(ms);
      });
    }

    async function startLoaded(answers: unknown[][]) {
      const calls = serve({ [LIST]: () => answers.shift() ?? answers.at(-1) });
      const hook = renderHook(() => useSchedules());
      await advance(0);
      return { calls, ...hook };
    }

    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('fetches again every few seconds while a last run is active, then slowly', async () => {
      const { calls, result } = await startLoaded([[running], [running], [finished]]);
      expect(result.current.schedules?.[0].last_run?.status).toBe('running');

      await advance(ACTIVE_REFRESH_MS);
      expect(calls).toHaveLength(2);
      await advance(ACTIVE_REFRESH_MS);
      expect(calls).toHaveLength(3);
      expect(result.current.schedules?.[0].last_run?.status).toBe('succeeded');

      // Nothing is active now: the next look is the slow one.
      await advance(IDLE_REFRESH_MS - ACTIVE_REFRESH_MS * 2);
      expect(calls).toHaveLength(3);
      await advance(ACTIVE_REFRESH_MS * 2);
      expect(calls).toHaveLength(4);
    });

    it('shows a schedule that fired while the page was open', async () => {
      const { result } = await startLoaded([[SCHEDULE], [running]]);
      expect(result.current.schedules?.[0].last_run).toBeNull();

      await advance(IDLE_REFRESH_MS);

      expect(result.current.schedules?.[0].last_run?.id).toBe(12);
    });

    it('waits while a change is saved, so an older refresh never undoes it', async () => {
      const off = { ...running, enabled: false, next_run_at: null };
      let release: () => void = () => {};
      const held = new Promise<unknown>((resolve) => {
        release = () => resolve(off);
      });
      const calls = serve({
        [LIST]: () => [running],
        [`PATCH ${API.schedule(SCHEDULE.id)}`]: () => held,
      });
      const { result } = renderHook(() => useSchedules());
      await advance(0);

      let saving: Promise<boolean> = Promise.resolve(true);
      act(() => {
        saving = result.current.actions.setEnabled(running, false);
      });
      await advance(ACTIVE_REFRESH_MS * 4);
      expect(calls.filter((call) => call.method === 'GET')).toHaveLength(1);

      await act(async () => {
        release();
        await saving;
      });
      expect(result.current.schedules?.[0].enabled).toBe(false);
      await advance(ACTIVE_REFRESH_MS);
      expect(calls.filter((call) => call.method === 'GET')).toHaveLength(2);
    });

    it('drops a refresh in flight when the screen goes away, and stops asking', async () => {
      const { calls, unmount } = await startLoaded([[running]]);
      await advance(ACTIVE_REFRESH_MS);
      expect(calls).toHaveLength(2);

      unmount();
      await advance(IDLE_REFRESH_MS * 2);

      expect(calls).toHaveLength(2);
    });

    it('tries again after a refresh fails, and keeps what it has meanwhile', async () => {
      const answers: unknown[] = [[running], refusal('Down.', 500, 'server_error'), [finished]];
      const calls = serve({ [LIST]: () => answers.shift() });
      const { result } = renderHook(() => useSchedules());
      await advance(0);

      await advance(ACTIVE_REFRESH_MS);
      expect(result.current.schedules?.[0].last_run?.status).toBe('running');
      expect(result.current.notice).toBeNull();
      await advance(ACTIVE_REFRESH_MS);

      expect(calls).toHaveLength(3);
      expect(result.current.schedules?.[0].last_run?.status).toBe('succeeded');
    });
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
