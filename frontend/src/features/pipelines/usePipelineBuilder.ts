import { useCallback, useEffect, useState } from 'react';

import * as pipelinesApi from '../../core/api/pipelines';
import type { Pipeline, PipelineStep, StepResult } from '../../core/api/types';
import { nextStage } from './stages';

function emptyPipeline(defaultModel: string): Pipeline {
  return {
    name: 'New Pipeline',
    steps: [{ order: 1, stage: 1, title: '', is_output: false, prompt: '', model: defaultModel }],
  };
}

/** State and transport for the builder screen, kept out of the component (§2). */
export function usePipelineBuilder(defaultModel: string) {
  const [pipeline, setPipeline] = useState<Pipeline>(() => emptyPipeline(defaultModel));
  const [saved, setSaved] = useState<Pipeline[]>([]);
  const [results, setResults] = useState<StepResult[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [status, setStatus] = useState<'idle' | 'saving' | 'running'>('idle');
  const [message, setMessage] = useState('');

  // Adopt the backend default once the model catalogue has loaded.
  useEffect(() => {
    if (!defaultModel) return;
    setPipeline((current) =>
      current.id === undefined && current.steps.length === 1 && current.steps[0].prompt === ''
        ? emptyPipeline(defaultModel)
        : current,
    );
  }, [defaultModel]);

  const refresh = useCallback(async () => {
    try {
      setSaved(await pipelinesApi.listPipelines());
    } catch (cause) {
      setMessage(cause instanceof Error ? cause.message : 'Could not load pipelines.');
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const reset = useCallback(() => {
    setPipeline(emptyPipeline(defaultModel));
    setResults([]);
    setElapsedMs(null);
    setMessage('');
  }, [defaultModel]);

  const select = useCallback((chosen: Pipeline) => {
    setPipeline(structuredClone(chosen));
    setResults([]);
    setElapsedMs(null);
    setMessage('');
  }, []);

  const patchStep = useCallback((index: number, patch: Partial<PipelineStep>) => {
    setPipeline((current) => ({
      ...current,
      steps: current.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    }));
  }, []);

  const addStep = useCallback(() => {
    setPipeline((current) => ({
      ...current,
      steps: [
        ...current.steps,
        {
          order: current.steps.length + 1,
          stage: nextStage(current.steps),
          title: '',
          is_output: false,
          prompt: '',
          model: defaultModel,
        },
      ],
    }));
  }, [defaultModel]);

  const removeStep = useCallback((index: number) => {
    setPipeline((current) => ({
      ...current,
      steps: current.steps
        .filter((_, i) => i !== index)
        .map((step, i) => ({ ...step, order: i + 1 })),
    }));
  }, []);

  const rename = useCallback((name: string) => {
    setPipeline((current) => ({ ...current, name }));
  }, []);

  const save = useCallback(async () => {
    setStatus('saving');
    setMessage('');
    try {
      const stored = await pipelinesApi.savePipeline(pipeline);
      setPipeline((current) => ({ ...current, id: stored.id }));
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
    [pipeline.id],
  );

  return {
    pipeline,
    saved,
    results,
    elapsedMs,
    status,
    message,
    actions: { reset, select, patchStep, addStep, removeStep, rename, save, run },
  };
}
