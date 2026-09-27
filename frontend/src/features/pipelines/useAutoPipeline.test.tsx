import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import * as pipelinesApi from '../../core/api/pipelines';
import type { Pipeline } from '../../core/api/types';
import { useAutoPipeline } from './useAutoPipeline';

const planned: Pipeline = {
  name: 'Launch plan',
  steps: [
    { order: 1, stage: 1, title: 'Facts', is_output: false, prompt: 'Find {input}', model: 'v/m' },
    { order: 2, stage: 2, title: 'Email', is_output: true, prompt: 'Write {input}', model: 'v/m' },
  ],
};

describe('useAutoPipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('adds and removes deliverables in the planned workflow', async () => {
    vi.spyOn(pipelinesApi, 'generatePipeline').mockResolvedValue({
      generated_pipeline: planned,
      available_models: ['v/m'],
    });
    const { result } = renderHook(() => useAutoPipeline());

    await act(async () => result.current.actions.generate('Create a launch plan', 'v/m'));
    act(() => result.current.actions.addOutput(1, false));
    expect(result.current.generated?.steps.map((step) => step.stage)).toEqual([1, 2, 3]);
    expect(result.current.generated?.steps[1].is_output).toBe(true);

    act(() => result.current.actions.removeStep(1));
    expect(result.current.generated?.steps.map((step) => step.order)).toEqual([1, 2]);
  });

  it('retains the saved identity for later edits', async () => {
    vi.spyOn(pipelinesApi, 'generatePipeline').mockResolvedValue({
      generated_pipeline: planned,
      available_models: ['v/m'],
    });
    vi.spyOn(pipelinesApi, 'savePipeline').mockResolvedValue({ ...planned, id: 7 });
    const { result } = renderHook(() => useAutoPipeline());

    await act(async () => result.current.actions.generate('Create a launch plan', 'v/m'));
    await act(async () => result.current.actions.save());

    expect(result.current.generated?.id).toBe(7);
  });
});
