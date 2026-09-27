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
  model: string;
  input_used: string;
  output: string;
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
