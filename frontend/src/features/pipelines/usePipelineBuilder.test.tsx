import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { usePipelineBuilder } from './usePipelineBuilder';

describe('usePipelineBuilder', () => {
  afterEach(() => vi.restoreAllMocks());

  it('opens a newly generated pipeline when the builder loads', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify([{ id: 7, name: 'Launch plan', steps: [] }]),
        { headers: { 'Content-Type': 'application/json' } },
      ),
    );

    const { result } = renderHook(() => usePipelineBuilder('vendor/model', 7));

    await waitFor(() => expect(result.current.pipeline.name).toBe('Launch plan'));
    expect(result.current.pipeline.id).toBe(7);
    expect(result.current.dirty).toBe(false);
  });
});
