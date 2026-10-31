import type { Pipeline } from './types';

/** Payloads of planning a pipeline with the planner model; nothing is saved. */

export interface GeneratedPipelineResponse {
  generated_pipeline: Pipeline;
  available_models: string[];
}

/** A question the planner asks before it plans a mission, with answers to pick from. */
export interface ClarifyingQuestion {
  question: string;
  /** Likely answers; the person may also write their own. */
  options: string[];
}

/** What the person answered to a question, or to all of them at once when typed. */
export interface PlanAnswer {
  question: string;
  answer: string;
}

/** A mission's plan (POST /api/pipelines/generate with `may_ask`): a team, or questions first. */
export interface MissionPlanResponse {
  /** Null when the planner asked `questions` instead. */
  generated_pipeline: Pipeline | null;
  questions: ClarifyingQuestion[];
  available_models: string[];
}

/** One difference between a draft and its proposed revision (POST /api/pipelines/revise). */
export interface PipelineChange {
  target: 'pipeline' | 'input' | 'step';
  kind: 'added' | 'removed' | 'changed';
  /** The pipeline's new name, the input's name, or the step's title ("Step N" without one). */
  label: string;
  /** A step's order: in the revision when added or changed, in the draft when removed. */
  order: number | null;
  /** For a change, the API field names that differ, e.g. "prompt" or "allowed_tools". */
  fields: string[];
}

export interface RevisedPipelineResponse {
  /** The whole revised pipeline; nothing is saved until the user saves it. */
  revised_pipeline: Pipeline;
  changes: PipelineChange[];
  available_models: string[];
}
