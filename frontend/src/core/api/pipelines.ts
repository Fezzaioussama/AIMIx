import { API } from './endpoints';
import { GENERATION_TIMEOUT_MS, request } from './client';
import type { GeneratedPipelineResponse, Pipeline, PipelineRunResponse } from './types';

export function listPipelines(): Promise<Pipeline[]> {
  return request<Pipeline[]>(API.pipelines).then((pipelines) => pipelines.map(normalizePipeline));
}

export function savePipeline(pipeline: Pipeline): Promise<Pipeline> {
  return request<Pipeline>(pipeline.id === undefined ? API.pipelines : API.pipeline(pipeline.id), {
    method: pipeline.id === undefined ? 'POST' : 'PUT',
    body: pipeline,
  }).then(normalizePipeline);
}

export function runPipeline(pipelineId: number, input: string): Promise<PipelineRunResponse> {
  // Pipelines chain several model calls, so they wait as long as a generation.
  return request<PipelineRunResponse>(API.runPipeline(pipelineId), {
    method: 'POST',
    body: { input },
    timeoutMs: GENERATION_TIMEOUT_MS,
  });
}

export function generatePipeline(
  description: string,
  plannerModel: string,
): Promise<GeneratedPipelineResponse> {
  return request<GeneratedPipelineResponse>(API.generatePipeline, {
    method: 'POST',
    body: { description, planner_model: plannerModel },
    timeoutMs: GENERATION_TIMEOUT_MS,
  }).then((response) => ({
    ...response,
    generated_pipeline: normalizePipeline(response.generated_pipeline),
  }));
}

/** Older saved pipelines and generated plans omit the new agent fields. */
function normalizePipeline(pipeline: Pipeline): Pipeline {
  return {
    ...pipeline,
    steps: pipeline.steps.map((step) => ({
      ...step,
      role: step.role ?? '',
      allowed_tools: step.allowed_tools ?? null,
    })),
  };
}
