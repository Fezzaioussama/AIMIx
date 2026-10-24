import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

  it('runs a saved pipeline with only its declared inputs', async () => {
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
        new Response(
          JSON.stringify({ pipeline_name: 'Posts', final_output: 'x', intermediate_results: [] }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
      );
    const { result } = renderHook(() => usePipelineBuilder('vendor/model', 7));
    await waitFor(() => expect(result.current.pipeline.id).toBe(7));

    await act(async () =>
      result.current.actions.run({ text: 'stale', values: { topic: 'bees', old: 'x' } }),
    );

    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"inputs":{"topic":"bees"}}');
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
