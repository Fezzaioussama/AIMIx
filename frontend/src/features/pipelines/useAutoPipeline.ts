import { useCallback, useState } from 'react';

import * as pipelinesApi from '../../core/api/pipelines';
import type { Pipeline, PipelineStep } from '../../core/api/types';
import { insertStep } from './stages';

type Status = 'idle' | 'generating' | 'saving';

/** Generation + save transport for the auto-pipeline screen (§2). */
export function useAutoPipeline() {
  const [generated, setGenerated] = useState<Pipeline | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const generate = useCallback(async (description: string, plannerModel: string) => {
    if (!description.trim()) {
      setErrorMessage('Please describe your workflow first.');
      return;
    }
    setStatus('generating');
    setErrorMessage('');
    setSuccessMessage('');
    setGenerated(null);
    try {
      const response = await pipelinesApi.generatePipeline(description, plannerModel);
      setGenerated(response.generated_pipeline);
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : 'Failed to generate pipeline.');
    } finally {
      setStatus('idle');
    }
  }, []);

  /** Returns the saved pipeline so the builder can open it. */
  const save = useCallback(async (): Promise<Pipeline | null> => {
    if (!generated) return null;
    setStatus('saving');
    setErrorMessage('');
    try {
      const stored = await pipelinesApi.savePipeline(generated);
      setGenerated(stored);
      setSuccessMessage(`Pipeline "${stored.name}" saved successfully!`);
      return stored;
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : 'Failed to save pipeline.');
      return null;
    } finally {
      setStatus('idle');
    }
  }, [generated]);

  const patchStep = useCallback((index: number, patch: Partial<PipelineStep>) => {
    setSuccessMessage('');
    setGenerated((current) =>
      current === null
        ? current
        : {
            ...current,
            steps: current.steps.map((step, i) => (i === index ? { ...step, ...patch } : step)),
          },
    );
  }, []);

  const rename = useCallback((name: string) => {
    setSuccessMessage('');
    setGenerated((current) => (current === null ? current : { ...current, name }));
  }, []);

  const addOutput = useCallback((stage: number, parallel: boolean) => {
    setSuccessMessage('');
    setGenerated((current) => {
      if (current === null) return null;
      const model = current.steps.find((step) => step.stage === stage)?.model ?? current.steps[0].model;
      return {
        ...current,
        steps: insertStep(current.steps, { model, stage, parallel, isOutput: true }),
      };
    });
  }, []);

  const removeStep = useCallback((index: number) => {
    setSuccessMessage('');
    setGenerated((current) =>
      current === null || current.steps.length === 1
        ? current
        : {
            ...current,
            steps: current.steps
              .filter((_, position) => position !== index)
              .map((step, position) => ({ ...step, order: position + 1 })),
          },
    );
  }, []);

  const reset = useCallback(() => {
    setGenerated(null);
    setErrorMessage('');
    setSuccessMessage('');
  }, []);

  return {
    generated,
    status,
    errorMessage,
    successMessage,
    actions: { generate, save, patchStep, rename, addOutput, removeStep, reset },
  };
}
