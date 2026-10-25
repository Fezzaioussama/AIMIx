import { useCallback, useEffect, useState } from 'react';

import * as pipelinesApi from '../../core/api/pipelines';
import { startRun } from '../../core/api/runs';
import type { Pipeline, PipelineInput, PipelineStep, Run } from '../../core/api/types';
import { runRequest, type RunDraft } from './pipelineInputs';
import { insertStep, nextStage } from './stages';
import { withoutStep } from './stepFlowEdits';

function emptyPipeline(defaultModel: string): Pipeline {
  return {
    name: 'New Pipeline',
    inputs: [],
    steps: [
      {
        order: 1,
        stage: 1,
        title: '',
        is_output: false,
        expected_output: '',
        prompt: '',
        model: defaultModel,
        role: '',
        allowed_tools: null,
        condition: null,
        review: null,
      },
    ],
  };
}

/**
 * State and transport for the builder screen, kept out of the component (§2).
 * `run` starts a background run; the page follows it (features/runs/useLatestRun).
 */
export function usePipelineBuilder(defaultModel: string, initialId?: number) {
  const [pipeline, setPipeline] = useState<Pipeline>(() => emptyPipeline(defaultModel));
  const [saved, setSaved] = useState<Pipeline[]>([]);
  /** `running`: a run is being started (the run itself is followed elsewhere). */
  const [status, setStatus] = useState<'idle' | 'saving' | 'running'>('idle');
  const [message, setMessage] = useState('');
  const [dirty, setDirty] = useState(false);

  const markChanged = useCallback(() => setDirty(true), []);

  // Adopt the backend default once the model catalogue has loaded.
  useEffect(() => {
    if (!defaultModel) return;
    setPipeline((current) =>
      current.id === undefined && current.steps.length === 1 && current.steps[0].model === ''
        ? { ...current, steps: [{ ...current.steps[0], model: defaultModel }] }
        : current,
    );
  }, [defaultModel]);

  const select = useCallback((chosen: Pipeline) => {
    setPipeline(structuredClone(chosen));
    setMessage('');
    setDirty(false);
  }, []);

  const refresh = useCallback(
    async (openId?: number) => {
      try {
        const pipelines = await pipelinesApi.listPipelines();
        setSaved(pipelines);
        const chosen = pipelines.find((candidate) => candidate.id === openId);
        if (chosen) select(chosen);
      } catch (cause) {
        setMessage(cause instanceof Error ? cause.message : 'Could not load pipelines.');
      }
    },
    [select],
  );

  useEffect(() => {
    void refresh(initialId);
  }, [refresh, initialId]);

  const reset = useCallback(() => {
    setPipeline(emptyPipeline(defaultModel));
    setMessage('');
    setDirty(false);
  }, [defaultModel]);

  const patchStep = useCallback(
    (index: number, patch: Partial<PipelineStep>) => {
      markChanged();
      setPipeline((current) => ({
        ...current,
        steps: current.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
      }));
    },
    [markChanged],
  );

  const addAtStage = useCallback(
    (stage: number | undefined, parallel: boolean) => {
      markChanged();
      setPipeline((current) => ({
        ...current,
        steps: insertStep(current.steps, {
          model: defaultModel,
          stage: stage ?? nextStage(current.steps),
          parallel,
        }),
      }));
    },
    [defaultModel, markChanged],
  );

  const addStep = useCallback(() => addAtStage(undefined, true), [addAtStage]);
  const addParallelStep = useCallback((stage: number) => addAtStage(stage, true), [addAtStage]);
  const addStepAfter = useCallback((stage: number) => addAtStage(stage, false), [addAtStage]);

  const removeStep = useCallback(
    (index: number) => {
      markChanged();
      setPipeline((current) => ({
        ...current,
        steps: withoutStep(current.steps, current.steps[index].order),
      }));
    },
    [markChanged],
  );

  const rename = useCallback(
    (name: string) => {
      markChanged();
      setPipeline((current) => ({ ...current, name }));
    },
    [markChanged],
  );

  const setInputs = useCallback(
    (inputs: PipelineInput[]) => {
      markChanged();
      setPipeline((current) => ({ ...current, inputs }));
    },
    [markChanged],
  );

  /** Swap in a whole new draft, e.g. an accepted revision; it stays unsaved until saved. */
  const replace = useCallback(
    (next: Pipeline) => {
      markChanged();
      setPipeline(next);
    },
    [markChanged],
  );

  const save = useCallback(async () => {
    setStatus('saving');
    setMessage('');
    try {
      const stored = await pipelinesApi.savePipeline(pipeline);
      setPipeline(stored);
      setDirty(false);
      setMessage('Pipeline saved.');
      await refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Failed to save pipeline.');
    } finally {
      setStatus('idle');
    }
  }, [pipeline, refresh]);

  /** Start a background run of the saved pipeline; the run, or null when it did not start. */
  const run = useCallback(
    async (draft: RunDraft): Promise<Run | null> => {
      if (pipeline.id === undefined) {
        setMessage('Please save the pipeline before running it.');
        return null;
      }
      if (dirty) {
        setMessage('Save your changes before running the pipeline.');
        return null;
      }
      setStatus('running');
      setMessage('');
      try {
        return await startRun(pipeline.id, runRequest(pipeline.inputs, draft));
      } catch (cause) {
        setMessage(cause instanceof Error ? cause.message : 'The run could not start.');
        return null;
      } finally {
        setStatus('idle');
      }
    },
    [dirty, pipeline.id, pipeline.inputs],
  );

  return {
    pipeline,
    saved,
    status,
    dirty,
    message,
    actions: {
      reset,
      select,
      patchStep,
      addStep,
      addParallelStep,
      addStepAfter,
      removeStep,
      rename,
      setInputs,
      replace,
      save,
      run,
    },
  };
}
