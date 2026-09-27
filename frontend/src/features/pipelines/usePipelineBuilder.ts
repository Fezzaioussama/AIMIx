import { useCallback, useEffect, useState } from 'react';

import * as pipelinesApi from '../../core/api/pipelines';
import type { Pipeline, PipelineStep, StepResult } from '../../core/api/types';
import { insertStep, nextStage } from './stages';

function emptyPipeline(defaultModel: string): Pipeline {
  return {
    name: 'New Pipeline',
    steps: [{ order: 1, stage: 1, title: '', is_output: false, prompt: '', model: defaultModel }],
  };
}

/** State and transport for the builder screen, kept out of the component (§2). */
export function usePipelineBuilder(defaultModel: string, initialId?: number) {
  const [pipeline, setPipeline] = useState<Pipeline>(() => emptyPipeline(defaultModel));
  const [saved, setSaved] = useState<Pipeline[]>([]);
  const [results, setResults] = useState<StepResult[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [status, setStatus] = useState<'idle' | 'saving' | 'running'>('idle');
  const [message, setMessage] = useState('');
  const [dirty, setDirty] = useState(false);

  const markChanged = useCallback(() => {
    setDirty(true);
    setResults([]);
    setElapsedMs(null);
  }, []);

  // Adopt the backend default once the model catalogue has loaded.
  useEffect(() => {
    if (!defaultModel) return;
    setPipeline((current) =>
      current.id === undefined && current.steps.length === 1 && current.steps[0].prompt === ''
        ? emptyPipeline(defaultModel)
        : current,
    );
  }, [defaultModel]);

  const select = useCallback((chosen: Pipeline) => {
    setPipeline(structuredClone(chosen));
    setResults([]);
    setElapsedMs(null);
    setMessage('');
    setDirty(false);
  }, []);

  const refresh = useCallback(async (openId?: number) => {
    try {
      const pipelines = await pipelinesApi.listPipelines();
      setSaved(pipelines);
      const chosen = pipelines.find((candidate) => candidate.id === openId);
      if (chosen) select(chosen);
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Could not load pipelines.');
    }
  }, [select]);

  useEffect(() => {
    void refresh(initialId);
  }, [refresh, initialId]);

  const reset = useCallback(() => {
    setPipeline(emptyPipeline(defaultModel));
    setResults([]);
    setElapsedMs(null);
    setMessage('');
    setDirty(false);
  }, [defaultModel]);

  const patchStep = useCallback((index: number, patch: Partial<PipelineStep>) => {
    markChanged();
    setPipeline((current) => ({
      ...current,
      steps: current.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    }));
  }, [markChanged]);

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

  const removeStep = useCallback((index: number) => {
    markChanged();
    setPipeline((current) => ({
      ...current,
      steps: current.steps
        .filter((_, i) => i !== index)
        .map((step, i) => ({ ...step, order: i + 1 })),
    }));
  }, [markChanged]);

  const rename = useCallback((name: string) => {
    markChanged();
    setPipeline((current) => ({ ...current, name }));
  }, [markChanged]);

  const save = useCallback(async () => {
    setStatus('saving');
    setMessage('');
    try {
      const stored = await pipelinesApi.savePipeline(pipeline);
      setPipeline((current) => ({ ...current, id: stored.id }));
      setDirty(false);
      setMessage('Pipeline saved.');
      await refresh();
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Failed to save pipeline.');
    } finally {
      setStatus('idle');
    }
  }, [pipeline, refresh]);

  const run = useCallback(
    async (input: string) => {
      if (pipeline.id === undefined) {
        setMessage('Please save the pipeline before running it.');
        return;
      }
      if (dirty) {
        setMessage('Save your changes before running the pipeline.');
        return;
      }
      setStatus('running');
      setMessage('');
      setResults([]);
      setElapsedMs(null);
      const started = performance.now();
      try {
        const response = await pipelinesApi.runPipeline(pipeline.id, input);
        setResults(response.intermediate_results);
        setElapsedMs(performance.now() - started);
      } catch (cause) {
        setMessage(cause instanceof Error ? cause.message : 'Execution failed.');
      } finally {
        setStatus('idle');
      }
    },
    [dirty, pipeline.id],
  );

  return {
    pipeline,
    saved,
    results,
    elapsedMs,
    status,
    dirty,
    message,
    actions: {
      reset, select, patchStep, addStep, addParallelStep, addStepAfter, removeStep, rename, save, run,
    },
  };
}
