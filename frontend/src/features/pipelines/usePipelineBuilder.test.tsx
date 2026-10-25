import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { usePipelineBuilder } from './usePipelineBuilder';

describe('usePipelineBuilder', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens a newly generated pipeline when the builder loads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([{ id: 7, name: 'Launch plan', steps: [] }]), {
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const { result } = renderHook(() => usePipelineBuilder('vendor/model', 7));

    await waitFor(() => expect(result.current.pipeline.name).toBe('Launch plan'));
    expect(result.current.pipeline.id).toBe(7);
    expect(result.current.dirty).toBe(false);
  });

  it('keeps agent edits when the default model arrives after a new draft is edited', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
    );
    const { result, rerender } = renderHook(({ model }) => usePipelineBuilder(model), {
      initialProps: { model: '' },
    });
    act(() =>
      result.current.actions.patchStep(0, {
        role: 'Researcher',
        allowed_tools: ['mcp_search'],
      }),
    );

    rerender({ model: 'vendor/model' });

    expect(result.current.pipeline.steps[0]).toMatchObject({
      model: 'vendor/model',
      role: 'Researcher',
      allowed_tools: ['mcp_search'],
    });
  });

  it('starts a background run of a saved pipeline with only its declared inputs', async () => {
    const saved = {
      id: 7,
      name: 'Posts',
      inputs: [{ name: 'topic', label: 'Topic', description: '' }],
      steps: [],
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify([saved]), { headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: 12, status: 'queued' }), {
          status: 202,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model', 7));
    await waitFor(() => expect(result.current.pipeline.id).toBe(7));

    let started: unknown;
    await act(async () => {
      started = await result.current.actions.run({
        text: 'stale',
        values: { topic: 'bees', old: 'x' },
      });
    });

    expect(fetchMock.mock.calls[1][0]).toBe(API.pipelineRuns(7));
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"inputs":{"topic":"bees"}}');
    expect(started).toMatchObject({ id: 12, status: 'queued' });
    expect(result.current.status).toBe('idle');
  });

  it('does not start a run of a pipeline with unsaved changes', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
      );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model'));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));

    let started: unknown;
    await act(async () => {
      started = await result.current.actions.run({ text: 'go', values: {} });
    });

    expect(started).toBeNull();
    expect(result.current.message).toBe('Please save the pipeline before running it.');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('keeps conditions and review loops pointing where they did as steps come and go', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
    );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model'));
    act(() => result.current.actions.addStepAfter(1));
    act(() => result.current.actions.addStepAfter(2));
    act(() => result.current.actions.patchStep(2, { title: 'Looks back' }));
    act(() =>
      result.current.actions.patchStep(2, {
        condition: { source: 'step:2', operator: 'not_empty', value: '' },
        review: { send_back_to_stage: 2, max_rounds: 1 },
      }),
    );

    // A step in a new stage after stage 1 is step 2 now, and the old steps move up.
    act(() => result.current.actions.addStepAfter(1));
    const titles = () => result.current.pipeline.steps.map((step) => step.title);
    expect(titles()).toEqual(['', '', '', 'Looks back']);
    const [, , , looking] = result.current.pipeline.steps;
    expect(looking.order).toBe(4);
    // It looked at old step 2, now step 3 in stage 3; it went back to stage 2, now stage 3.
    expect(looking.condition?.source).toBe('step:3');
    expect(looking.review?.send_back_to_stage).toBe(3);

    // Removing the step it looks at leaves it looking at nothing, never at another step.
    act(() => result.current.actions.removeStep(2));
    const [, , last] = result.current.pipeline.steps;
    expect(last.title).toBe('Looks back');
    expect(last.condition?.source).toBe('step:0');
  });

  it('marks the pipeline changed when its inputs are edited', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
    );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model'));

    act(() =>
      result.current.actions.setInputs([{ name: 'topic', label: 'Topic', description: '' }]),
    );

    expect(result.current.pipeline.inputs.map((field) => field.name)).toEqual(['topic']);
    expect(result.current.dirty).toBe(true);
  });

  it('takes an accepted revision as the new, unsaved draft', () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify([]), { headers: { 'Content-Type': 'application/json' } }),
      );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model'));
    const revised = { ...result.current.pipeline, id: 7, name: 'Revised' };

    act(() => result.current.actions.replace(revised));

    expect(result.current.pipeline).toEqual(revised);
    expect(result.current.dirty).toBe(true);
    // Only the saved-list request: replacing never saves.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
