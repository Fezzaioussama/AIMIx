import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Pipeline } from '../../core/api/types';
import { json, PLAN, SAVED, routeFetch, storeAs } from './testData';
import { AUTOSAVE_DELAY_MS, DEFAULT_MISSION_NAME, useMissionTeam } from './useMissionTeam';

describe('useMissionTeam', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('loads a saved mission by its id', async () => {
    routeFetch({ 'GET /api/pipelines/7/': SAVED });
    const { result } = renderHook(() => useMissionTeam(7, null));

    expect(result.current.status).toBe('loading');
    expect(result.current.pipeline).toBeNull();
    await waitFor(() => expect(result.current.pipeline).toEqual(SAVED));

    expect(result.current.status).toBe('idle');
    expect(result.current.unsaved).toBe(false);
    expect(result.current.error).toBe('');
  });

  it('says plainly that a mission that does not exist was not found', async () => {
    routeFetch({
      'GET /api/pipelines/7/': () =>
        json({ error: 'not_found', detail: 'Pipeline 7 was not found.' }, 404),
    });
    const { result } = renderHook(() => useMissionTeam(7, null));

    await waitFor(() => expect(result.current.status).toBe('idle'));

    expect(result.current.pipeline).toBeNull();
    expect(result.current.error).toMatch(/not found.*deleted/i);
  });

  it('keeps another reason for a failed load', async () => {
    routeFetch({
      'GET /api/pipelines/7/': () =>
        json({ error: 'server_error', detail: 'Database is down.' }, 500),
    });
    const { result } = renderHook(() => useMissionTeam(7, null));

    await waitFor(() => expect(result.current.error).toBe('Database is down.'));
  });

  it('cancels the load when the screen is left', () => {
    let signal: AbortSignal | null | undefined;
    routeFetch({
      'GET /api/pipelines/7/': (init) => {
        signal = init?.signal;
        return new Promise(() => {});
      },
    });
    const { unmount } = renderHook(() => useMissionTeam(7, null));

    unmount();

    expect(signal?.aborted).toBe(true);
  });

  it('starts from the tab’s draft for a mission never saved', () => {
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    expect(result.current.pipeline).toEqual(PLAN);
    expect(result.current.unsaved).toBe(true);
  });

  it('saves a new team once, then only when it has changed', async () => {
    const server = routeFetch({ 'POST /api/pipelines/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    let first: Awaited<ReturnType<typeof result.current.save>> | undefined;
    await act(async () => {
      first = await result.current.save();
    });
    await act(async () => {
      await result.current.save();
    });

    expect(first?.pipeline?.id).toBe(7);
    expect(result.current.pipeline?.id).toBe(7);
    expect(result.current.unsaved).toBe(false);
    expect(server.to('POST', '/api/pipelines/')).toHaveLength(1);
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(0);
  });

  it('names a team that has no name', async () => {
    const server = routeFetch({ 'POST /api/pipelines/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, { ...PLAN, name: '  ' }));

    await act(async () => {
      await result.current.save();
    });

    expect((server.calls[0].body as Pipeline).name).toBe(DEFAULT_MISSION_NAME);
  });

  it('makes two saves at once one request', async () => {
    const server = routeFetch({ 'POST /api/pipelines/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    await act(async () => {
      await Promise.all([result.current.save(), result.current.save()]);
    });

    expect(server.to('POST', '/api/pipelines/')).toHaveLength(1);
  });

  it('reports why a save failed and stays unsaved', async () => {
    routeFetch({
      'POST /api/pipelines/': () =>
        json({ error: 'validation_error', detail: 'Prompt is empty.' }, 400),
    });
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    let outcome: Awaited<ReturnType<typeof result.current.save>> | undefined;
    await act(async () => {
      outcome = await result.current.save();
    });

    expect(outcome).toEqual({ pipeline: null, error: 'Prompt is empty.' });
    expect(result.current.error).toBe('Prompt is empty.');
    expect(result.current.unsaved).toBe(true);
  });

  it('edits and removes agents by their order, renumbering after a removal', () => {
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    act(() => result.current.patchStep(2, { role: 'Lead analyst' }));
    expect(result.current.pipeline?.steps[1].role).toBe('Lead analyst');

    act(() => result.current.removeStep(1));
    expect(result.current.pipeline?.steps).toHaveLength(1);
    expect(result.current.pipeline?.steps[0]).toMatchObject({ order: 1, role: 'Lead analyst' });
  });

  it('saves a saved mission’s edits after a pause, once, keeping the team as it is', async () => {
    vi.useFakeTimers();
    const server = routeFetch({ 'PUT /api/pipelines/7/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, SAVED));

    act(() => result.current.patchStep(1, { prompt: 'New prompt {input}' }));
    const edited = result.current.pipeline;
    expect(result.current.unsaved).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 1);
    });
    expect(server.calls).toHaveLength(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2);
    });

    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1);
    expect(result.current.unsaved).toBe(false);
    // A proposal made for this team must stay valid: saving is not a change.
    expect(result.current.pipeline).toBe(edited);
  });

  it('starts the pause over with each edit', async () => {
    vi.useFakeTimers();
    const server = routeFetch({ 'PUT /api/pipelines/7/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, SAVED));

    act(() => result.current.patchStep(1, { role: 'A' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100);
    });
    act(() => result.current.patchStep(1, { role: 'AB' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 100);
    });
    expect(server.calls).toHaveLength(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1);
    expect((server.calls[0].body as Pipeline).steps[0].role).toBe('AB');
  });

  it('never saves a mission that was not saved before until it is run', async () => {
    vi.useFakeTimers();
    const server = routeFetch({ 'POST /api/pipelines/': storeAs(7) });
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    act(() => result.current.patchStep(1, { role: 'Changed' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS * 3);
    });

    expect(server.calls).toHaveLength(0);
  });

  it('keeps edits made while it was saving, and saves them next', async () => {
    vi.useFakeTimers();
    let finish: () => void = () => {};
    const server = routeFetch({
      'POST /api/pipelines/': (init) =>
        new Promise((resolve) => {
          finish = () => resolve(storeAs(7)(init));
        }),
      'PUT /api/pipelines/7/': storeAs(7),
    });
    const { result } = renderHook(() => useMissionTeam(undefined, PLAN));

    let saving: Promise<unknown> = Promise.resolve();
    act(() => {
      saving = result.current.save();
    });
    act(() => result.current.patchStep(1, { role: 'Edited meanwhile' }));
    await act(async () => {
      finish();
      await saving;
    });

    expect(result.current.pipeline).toMatchObject({ id: 7 });
    expect(result.current.pipeline?.steps[0].role).toBe('Edited meanwhile');
    expect(result.current.unsaved).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS + 1);
    });
    expect(server.to('PUT', '/api/pipelines/7/')).toHaveLength(1);
    expect(result.current.unsaved).toBe(false);
  });

  it('adopts a team made elsewhere without calling it changed', () => {
    const { result } = renderHook(() => useMissionTeam(undefined, null));

    act(() => result.current.adopt(SAVED));

    expect(result.current.pipeline).toEqual(SAVED);
    expect(result.current.unsaved).toBe(false);
  });

  it('calls a replaced team changed', () => {
    const { result } = renderHook(() => useMissionTeam(undefined, null));
    act(() => result.current.adopt(SAVED));

    act(() => result.current.replace({ ...SAVED, name: 'Renamed' }));

    expect(result.current.unsaved).toBe(true);
  });
});
