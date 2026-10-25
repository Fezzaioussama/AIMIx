import { API } from './endpoints';
import { GENERATION_TIMEOUT_MS, request } from './client';
import type { GeneratedPipelineResponse, Pipeline, RevisedPipelineResponse } from './types';

export function listPipelines(): Promise<Pipeline[]> {
  return request<Pipeline[]>(API.pipelines).then((pipelines) => pipelines.map(normalizePipeline));
}

/** One of the signed-in user's pipelines; another user's is a 404 `not_found`. */
export function getPipeline(pipelineId: number, signal?: AbortSignal): Promise<Pipeline> {
  return request<Pipeline>(API.pipeline(pipelineId), { signal }).then(normalizePipeline);
}

export function savePipeline(pipeline: Pipeline): Promise<Pipeline> {
  return request<Pipeline>(pipeline.id === undefined ? API.pipelines : API.pipeline(pipeline.id), {
    method: pipeline.id === undefined ? 'POST' : 'PUT',
    body: pipeline,
  }).then(normalizePipeline);
}

/** Plans a pipeline from a description; nothing is saved. No `plannerModel` means the default. */
export function generatePipeline(
  description: string,
  plannerModel?: string,
  signal?: AbortSignal,
): Promise<GeneratedPipelineResponse> {
  return request<GeneratedPipelineResponse>(API.generatePipeline, {
    method: 'POST',
    body: { description, planner_model: plannerModel || undefined },
    timeoutMs: GENERATION_TIMEOUT_MS,
    signal,
  }).then((response) => ({
    ...response,
    generated_pipeline: normalizePipeline(response.generated_pipeline),
  }));
}

/**
 * Asks the planner to change a draft as `instruction` says. The draft may be unsaved;
 * nothing is saved. No `plannerModel` means the account's default model.
 */
export function revisePipeline(
  pipeline: Pipeline,
  instruction: string,
  plannerModel?: string,
  signal?: AbortSignal,
): Promise<RevisedPipelineResponse> {
  return request<RevisedPipelineResponse>(API.revisePipeline, {
    method: 'POST',
    body: { pipeline, instruction, planner_model: plannerModel || undefined },
    timeoutMs: GENERATION_TIMEOUT_MS,
    signal,
  }).then((response) => ({
    ...response,
    revised_pipeline: normalizePipeline(response.revised_pipeline),
  }));
}

/**
 * Older saved pipelines and generated plans omit the newer agent, I/O and flow fields, and
 * a planner may leave a step without a prompt.
 */
export function normalizePipeline(pipeline: Pipeline): Pipeline {
  return {
    ...pipeline,
    inputs: pipeline.inputs ?? [],
    steps: pipeline.steps.map((step) => ({
      ...step,
      prompt: step.prompt ?? '',
      role: step.role ?? '',
      allowed_tools: step.allowed_tools ?? null,
      expected_output: step.expected_output ?? '',
      condition: step.condition ?? null,
      review: step.review ?? null,
    })),
  };
}
