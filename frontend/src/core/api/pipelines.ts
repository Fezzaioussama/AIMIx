import { API } from './endpoints';
import { request } from './client';
import type { GeneratedPipelineResponse, Pipeline, PipelineRunResponse } from './types';

export function listPipelines(): Promise<Pipeline[]> {
  return request<Pipeline[]>(API.pipelines);
}

export function savePipeline(pipeline: Pipeline): Promise<Pipeline> {
  return request<Pipeline>(API.pipelines, { method: 'POST', body: pipeline });
}

export function runPipeline(pipelineId: number, input: string): Promise<PipelineRunResponse> {
  // Pipelines chain several model calls, so they need more headroom than the
  // default request timeout.
  return request<PipelineRunResponse>(API.runPipeline(pipelineId), {
    method: 'POST',
    body: { input },
    timeoutMs: 180_000,
  });
}

export function generatePipeline(
  description: string,
  plannerModel: string,
): Promise<GeneratedPipelineResponse> {
  return request<GeneratedPipelineResponse>(API.generatePipeline, {
    method: 'POST',
    body: { description, planner_model: plannerModel },
    timeoutMs: 120_000,
  });
}
