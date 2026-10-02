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
  /** Agent identity and specialization; empty means the default agent role. */
  role: string;
  /** null grants all configured tools; an empty list grants none. */
  allowed_tools: string[] | null;
}

export interface AgentTool {
  name: string;
  description: string;
  source: string;
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
  tool_calls: { name: string; status: 'success' | 'error' }[];
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
