/**
 * Payload contracts shared by every feature (AGENTS.md §8: declared once,
 * imported — never redeclared per component).
 */

export interface AuthTokens {
  access: string;
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
  /** What the step's agent must deliver; empty leaves it to the prompt. */
  expected_output: string;
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

/** A named value every run is given; any step's prompt inserts it as `{name}`. */
export interface PipelineInput {
  name: string;
  /** Shown on the run form; empty falls back to the name. */
  label: string;
  /** Tells the person running the pipeline what to enter. */
  description: string;
}

export interface Pipeline {
  id?: number;
  name: string;
  /** Named run inputs; empty means the pipeline runs on one free-text input. */
  inputs: PipelineInput[];
  steps: PipelineStep[];
}

/** Body of a run: free text, or a value for each input the pipeline declares. */
export interface PipelineRunRequest {
  input?: string;
  inputs?: Record<string, string>;
}

/** A document read into text, ready to become a run input (POST /api/documents/extract). */
export interface ExtractedDocument {
  filename: string;
  /** Lower-case extension without the dot, e.g. "pdf". */
  format: string;
  text: string;
  characters: number;
  /** Page count for paged formats (PDF), else null. */
  pages: number | null;
  /** True when part of the document was left out (size or page limit). */
  truncated: boolean;
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

export interface ModelsResponse {
  models: string[];
  default: string;
}

/** Where the key a provider uses comes from. The key itself is never sent back. */
export type KeySource = 'saved' | 'environment' | 'none';

export interface ProviderSettings {
  name: string;
  key_source: KeySource;
  /** Last characters of the saved key; empty when none is saved. */
  key_hint: string;
  default_model: string;
  /** The provider's catalogue, its default first. */
  models: string[];
}

export interface LLMSettings {
  /** The provider this account's chat, pipelines and planner use. */
  provider: string;
  providers: ProviderSettings[];
}

export interface ProviderSettingsUpdate {
  name: string;
  default_model: string;
  /** Omit to keep the saved key. */
  api_key?: string;
}

export interface LLMSettingsUpdate {
  provider: string;
  providers: ProviderSettingsUpdate[];
}
