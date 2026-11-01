import { API } from './endpoints';
import { GENERATION_TIMEOUT_MS, request } from './client';
import type { PlanDocument } from './planningTypes';
import type {
  GeneratedPipelineResponse,
  MissionPlanResponse,
  Pipeline,
  PlanAnswer,
  RevisedPipelineResponse,
} from './types';

/**
 * Limits of a mission's plan request. They mirror backend/api/schemas/planning.py, which
 * decides: the longest description, and how many documents go with it, each as the start
 * of its text.
 */
export const PLAN_DESCRIPTION_MAX_LENGTH = 20_000;
export const MAX_PLAN_DOCUMENTS = 5;
export const PLAN_DOCUMENT_EXCERPT_CHARS = 2000;
/** A document's name: its file name, or the address a page's link ended at. */
export const PLAN_DOCUMENT_NAME_MAX_LENGTH = 2048;
/** The run input a plan made with documents always has; their text goes there on each run. */
export const DOCUMENTS_INPUT_NAME = 'documents';

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

/** What a mission is planned from. */
export interface MissionPlanRequest {
  description: string;
  /** Answers to the planner's earlier questions. */
  answers: PlanAnswer[];
  /** The planner may answer with questions instead of a team. */
  mayAsk: boolean;
  /** The documents the person attached (at most MAX_PLAN_DOCUMENTS); none sends no field. */
  documents?: PlanDocument[];
}

/**
 * Plans a mission; nothing is saved. With `mayAsk`, the planner may answer with questions
 * instead of a team when the description is unclear; once `answers` are given it plans
 * and asks nothing more. With `documents`, the plan has a run input for their text.
 */
export function planMission(
  plan: MissionPlanRequest,
  signal?: AbortSignal,
): Promise<MissionPlanResponse> {
  const { description, answers, mayAsk, documents = [] } = plan;
  return request<MissionPlanResponse>(API.generatePipeline, {
    method: 'POST',
    body: {
      description,
      may_ask: mayAsk,
      answers,
      ...(documents.length > 0 ? { documents } : {}),
    },
    timeoutMs: GENERATION_TIMEOUT_MS,
    signal,
  }).then((response) => ({
    ...response,
    generated_pipeline:
      response.generated_pipeline && normalizePipeline(response.generated_pipeline),
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
