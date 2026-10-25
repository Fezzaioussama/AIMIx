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

/**
 * Spending limits of a run, set when it starts or raised when it resumes. A limit
 * left out keeps its default (the server's, or the run's own on resume).
 */
export interface RunBudget {
  /** Stop once the model calls have cost this much, in USD. */
  max_cost_usd?: number;
  /** Stop once the model calls have used this many tokens, in and out. */
  max_tokens?: number;
}

/** Body of a run: free text, or a value for each input the pipeline declares. */
export interface PipelineRunRequest extends RunBudget {
  input?: string;
  inputs?: Record<string, string>;
}

/** Tokens and cost of model calls: a run's, a pipeline's or a period's. */
export interface Usage {
  input_tokens: number;
  output_tokens: number;
  /** USD, the known costs added up; null when none is known. */
  cost_usd: number | null;
  /** False when some tokens came from a model whose cost is unknown. */
  cost_complete: boolean;
}

/** A document read into text, ready to become a run input (POST /api/documents/extract). */
export interface ExtractedDocument {
  filename: string;
  /** Lower-case extension without the dot, e.g. "pdf". */
  format: string;
  text: string;
  characters: number;
  /** Page count for paged formats (PDF pages, slides, TIFF pages), else null. */
  pages: number | null;
  /** True when part of the document was left out (a limit, or pages OCR skipped). */
  truncated: boolean;
}

/** A file in the user's workspace, the folder their agents read and save to. */
export interface WorkspaceFile {
  /** Relative to the workspace, '/'-separated, e.g. "reports/q3.pdf". */
  path: string;
  /** In bytes. */
  size: number;
  /** ISO 8601, UTC. */
  modified_at: string;
  /** Lower-case extension without the dot, e.g. "pdf"; empty when there is none. */
  type: string;
}

/** GET /api/files: the files, newest first, and the limits that apply to them. */
export interface FileListing {
  files: WorkspaceFile[];
  /** The sum of the files' sizes: what the storage limit counts. */
  used_bytes: number;
  quota_bytes: number;
  /** The largest file one upload may be. */
  max_file_bytes: number;
  /** What an upload may be, lower-case with the dot, e.g. ".pdf". */
  allowed_extensions: string[];
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

/** Where a run is. `queued` and `running` are active; the rest are final. */
export type RunStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted';

/** Where one step of a run is. */
export type RunStepStatus = 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface RunError {
  code: string;
  detail: string;
}

/** One step of a run: its result fields (filled once it succeeded) and its progress. */
export interface RunStep extends StepResult {
  status: RunStepStatus;
  error: RunError | null;
  started_at: string | null;
  finished_at: string | null;
  /** What its model calls used, over every attempt (a failed step keeps what it spent). */
  input_tokens: number;
  output_tokens: number;
  /** USD; null when the cost of its model is unknown. */
  cost_usd: number | null;
}

/** A run in the history list (GET /api/runs): no inputs, outputs or steps. */
export interface RunSummary {
  id: number;
  /** null once the pipeline was deleted; the run keeps its name. */
  pipeline_id: number | null;
  pipeline_name: string;
  status: RunStatus;
  error: RunError | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  /** The run's spending limits; null is no limit. */
  max_cost_usd: number | null;
  max_tokens: number | null;
  /** What its model calls used and cost so far, over every attempt. */
  usage: Usage;
}

/** A whole run (GET /api/runs/<id>), polled while it is active. */
export interface Run extends RunSummary {
  /** The free text it was started with ("" when the pipeline has named inputs). */
  input: string;
  /** The value of each named input it was started with. */
  inputs: Record<string, string>;
  final_output: string;
  /** The pipeline as it was when the run started; later edits never change it. */
  definition: { name: string; inputs: PipelineInput[]; steps: PipelineStep[] };
  steps: RunStep[];
}

export interface RunPage {
  items: RunSummary[];
  /** How many runs match in all. */
  total: number;
}

/** What one pipeline's runs used; a deleted pipeline keeps its last name. */
export interface PipelineUsage {
  /** null once the pipeline was deleted. */
  pipeline_id: number | null;
  pipeline_name: string;
  runs: number;
  usage: Usage;
}

/** GET /api/usage: what the account's runs of the last `days` days used. */
export interface UsageReport {
  days: number;
  since: string;
  runs: number;
  usage: Usage;
  /** Costliest first. */
  pipelines: PipelineUsage[];
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

/** A ready-made mission in the template gallery (GET /api/templates). */
export interface MissionTemplate {
  slug: string;
  title: string;
  /** What the gallery filters by, e.g. "Research". */
  category: string;
  /** One line for the card. */
  description: string;
  /** What the user fills in on every run of the pipeline. */
  inputs: PipelineInput[];
  /** How many agents the pipeline has. */
  step_count: number;
  stage_count: number;
}

/** A saved header of an integration. Its value is never sent back. */
export interface IntegrationHeader {
  name: string;
  /** Last characters of the value; empty when the value is too short to hint at. */
  hint: string;
}

/** One of the account's own MCP servers (Settings → Integrations). */
export interface Integration {
  id: number;
  /** Prefixes its tools' names: `<name>_<tool>`. */
  name: string;
  url: string;
  enabled: boolean;
  headers: IntegrationHeader[];
  created_at: string;
}

export interface IntegrationHeaderInput {
  name: string;
  /** Omit (or null) on an update to keep the value saved under this name. */
  value?: string | null;
}

export interface IntegrationInput {
  name: string;
  url: string;
  enabled?: boolean;
  headers: IntegrationHeaderInput[];
}

/** Omitted fields keep their value; `headers`, when sent, is the complete list. */
export interface IntegrationPatch {
  name?: string;
  url?: string;
  enabled?: boolean;
  headers?: IntegrationHeaderInput[];
}

/** A tool a connection test found, named as agents and `allowed_tools` use it. */
export interface IntegrationTool {
  name: string;
  description: string;
}

export interface IntegrationTestResult {
  tools: IntegrationTool[];
}
