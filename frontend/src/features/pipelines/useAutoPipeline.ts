import { useCallback, useState } from 'react';

import * as pipelinesApi from '../../core/api/pipelines';
import type { Pipeline, PipelineStep } from '../../core/api/types';

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

  /** Returns true only when the pipeline reached the backend. */
  const save = useCallback(async (): Promise<boolean> => {
    if (!generated) return false;
    setStatus('saving');
    setErrorMessage('');
    try {
      const stored = await pipelinesApi.savePipeline(generated);
      setSuccessMessage(`Pipeline "${stored.name}" saved successfully!`);
      return true;
    } catch (cause) {
      setErrorMessage(cause instanceof Error ? cause.message : 'Failed to save pipeline.');
      return false;
    } finally {
      setStatus('idle');
    }
  }, [generated]);

  const patchStep = useCallback((index: number, patch: Partial<PipelineStep>) => {
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
    setGenerated((current) => (current === null ? current : { ...current, name }));
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
    actions: { generate, save, patchStep, rename, reset },
  };
}
