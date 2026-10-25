import type { Pipeline, PipelineStep, RevisedPipelineResponse } from '../../core/api/types';

/** Shared fixtures for the revise hook and panel tests. */
export function testStep(order: number, stage: number, title: string): PipelineStep {
  return {
    order,
    stage,
    title,
    is_output: stage > 1,
    expected_output: '',
    prompt: `${title} for {product}: {input}`,
    model: 'vendor/model',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
  };
}

/** A saved draft: revising it must keep its id. */
export const draft: Pipeline = {
  id: 7,
  name: 'Launch kit',
  inputs: [{ name: 'product', label: 'Product', description: '' }],
  steps: [testStep(1, 1, 'Research'), testStep(2, 2, 'Marketing copy')],
};

export const revision: RevisedPipelineResponse = {
  revised_pipeline: {
    name: 'Launch kit',
    inputs: draft.inputs,
    steps: [...draft.steps, testStep(3, 2, 'SEO keywords')],
  },
  changes: [{ target: 'step', kind: 'added', label: 'SEO keywords', order: 3, fields: [] }],
  available_models: ['vendor/model'],
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A fetch that never answers but fails as a browser does once its signal aborts. */
export function pendingFetch(_path: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  return new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () =>
      reject(new DOMException('The operation was aborted.', 'AbortError')),
    );
  });
}
