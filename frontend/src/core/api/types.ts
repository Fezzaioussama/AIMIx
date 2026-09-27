/**
 * Payload contracts shared by every feature (AGENTS.md §8: declared once,
 * imported — never redeclared per component).
 */

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface PipelineStep {
  id?: number;
  order: number;
  /** Steps sharing a stage run in parallel; stages run in ascending order. */
  stage: number;
  /** Short name shown in the UI; may be empty. */
  title: string;
  /** A deliverable of the pipeline rather than intermediate work. */
  is_output: boolean;
  prompt: string;
  model: string;
}

export interface Pipeline {
  id?: number;
  name: string;
  steps: PipelineStep[];
}

export interface StepResult {
  step_order: number;
  stage: number;
  title: string;
  model: string;
  input_used: string;
  output: string;
  /** Decided by the backend: marked steps, or the last stage if none are marked. */
  is_output: boolean;
}

export interface PipelineRunResponse {
  pipeline_name: string;
  final_output: string;
  intermediate_results: StepResult[];
}

export interface GeneratedPipelineResponse {
  generated_pipeline: Pipeline;
  available_models: string[];
}

export interface ModelsResponse {
  models: string[];
  default: string;
}
