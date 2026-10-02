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
});
