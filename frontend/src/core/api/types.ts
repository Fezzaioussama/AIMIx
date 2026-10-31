/**
 * Payload contracts shared by every feature (AGENTS.md §8: declared once,
 * imported — never redeclared per component).
 */

export interface AuthTokens {
  access: string;
}

/** How a condition compares text (trimmed, ignoring case); the words are in features/pipelines/stepFlow. */
export type ConditionOperator =
  'contains' | 'not_contains' | 'equals' | 'not_equals' | 'is_empty' | 'not_empty';

/**
 * "Run this step only if ...": the step is skipped when it does not hold. `source` is what
 * it looks at: "previous_output" (the step's `{input}`), "input:<name>" (a named input) or
 * "step:<order>" (the result of a step in an earlier stage). `value` is what it compares
 * with; operators that take none (`is_empty`, `not_empty`) ignore it.
 */
export interface StepCondition {
  source: string;
  operator: ConditionOperator;
  value: string;
}

/**
 * Makes a step a reviewer that can send the work back for fixes: the stages from
 * `send_back_to_stage` (an earlier stage) up to the reviewer's run again, at most
 * `max_rounds` (1 to 5) times, so those stages run at most `1 + max_rounds` times.
 */
export interface StepReview {
  send_back_to_stage: number;
  max_rounds: number;
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
  /** The step runs only while this holds; null always runs it. */
  condition: StepCondition | null;
  /** Makes the step a reviewer that can send the work back; null for any other step. */
  review: StepReview | null;
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
 * Spending limits of a run, set when it starts or raised when it resumes. A limit left out
 * keeps its default (the server's, or the run's own on resume); none may pass the server's.
 */
export interface RunBudget {
  /** Stop once the model calls have cost this much, in USD. */
  max_cost_usd?: number | null;
  /** Stop once the model calls have used this many tokens, in and out. */
  max_tokens?: number | null;
}

/** A run's or a schedule's saved limits; null is none of its own. */
export type SpendingLimits = { [Limit in keyof RunBudget]-?: number | null };

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

/** What a recorded clip said (POST /api/voice/transcribe). */
export interface Transcript {
  transcript: string;
  /** How long the clip was, as the speech model measured it; null when it did not say. */
  duration_ms: number | null;
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

/**
 * Where a run is. `queued`, `running` and `waiting` (a tool call waits for the
 * owner's approval) are active; the rest are final.
 */
export type RunStatus =
  'queued' | 'running' | 'waiting' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted';

/**
 * Where one step of a run is. `skipped`: its condition did not hold, so it did not run; it is
 * final, like `succeeded`, and a resumed run keeps it.
 */
export type RunStepStatus =
  'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'skipped';

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
  /**
   * The review round its row is in: 1, or more when a review loop sent the work back and
   * the step ran again (the row then holds the newest round).
   */
  rounds: number;
  /** What a reviewer's last answer decided; null for any other step, and when it gave none. */
  verdict: 'pass' | 'revise' | null;
}

/** Where a tool call that asks the run's owner first is. Only `pending` changes. */
export type ApprovalStatus = 'pending' | 'approved' | 'declined' | 'expired';

/** A tool call held until the run's owner approves or declines it (`Run.pending_approvals`). */
export interface RunApproval {
  id: number;
  /** The run step whose agent wants to use the tool. */
  step_order: number;
  /** The exact tool name, e.g. "crm_send_email". */
  tool_name: string;
  /** Where the tool comes from: an integration's name, "MCP" or "AIMIx". */
  tool_source: string;
  tool_description: string;
  /** The call's arguments; long text values may be shortened (`arguments_truncated`). */
  arguments: Record<string, unknown>;
  arguments_truncated: boolean;
  status: ApprovalStatus;
  created_at: string;
  /** Unanswered by then, the request expires and the tool does not act. */
  expires_at: string;
}

/** What started a run: its owner (by hand or through the API), a schedule, or the chat agent. */
export type RunTrigger = 'manual' | 'schedule' | 'chat';

/** A run in the history list (GET /api/runs): no inputs, outputs or steps. */
export interface RunSummary extends SpendingLimits {
  id: number;
  /** null once the pipeline was deleted; the run keeps its name. */
  pipeline_id: number | null;
  pipeline_name: string;
  trigger: RunTrigger;
  /** The schedule that started it; null for other runs, and once that schedule is deleted. */
  schedule_id: number | null;
  status: RunStatus;
  error: RunError | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
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
  /** Tool calls waiting for your answer, oldest first; empty unless the run is `waiting`. */
  pending_approvals: RunApproval[];
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

// Planning payloads (POST /api/pipelines/generate and /revise) live in planningTypes.ts.
export type {
  ClarifyingQuestion,
  GeneratedPipelineResponse,
  MissionPlanResponse,
  PipelineChange,
  PlanAnswer,
  RevisedPipelineResponse,
} from './planningTypes';

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
  /** In a run, its tools wait for your OK before they act. */
  require_approval: boolean;
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
  /** Defaults to true: the integration's tools ask before they act. */
  require_approval?: boolean;
  headers: IntegrationHeaderInput[];
}

/** Omitted fields keep their value; `headers`, when sent, is the complete list. */
export interface IntegrationPatch {
  name?: string;
  url?: string;
  enabled?: boolean;
  require_approval?: boolean;
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

/** How often a schedule runs; hourly is the most often. */
export type ScheduleFrequency = 'hourly' | 'daily' | 'weekdays' | 'weekly' | 'monthly';

/** The newest run a schedule started. */
export interface ScheduleLastRun {
  id: number;
  status: RunStatus;
  created_at: string;
}

/** When a schedule runs (and the body of POST /api/schedules/preview). */
export interface ScheduleTiming {
  frequency: ScheduleFrequency;
  /** "HH:MM" on a 24-hour clock in `timezone`; an hourly schedule uses the minutes only. */
  time: string;
  /** 0 is Monday, 6 Sunday. Weekly schedules only. */
  weekday?: number | null;
  /** 1 to 31; past the end of a shorter month, its last day. Monthly schedules only. */
  day_of_month?: number | null;
  /** An IANA time zone name, e.g. "Europe/Paris". */
  timezone: string;
}

/** A pipeline started on its own at a preset frequency (GET /api/schedules). */
export interface Schedule extends ScheduleTiming, SpendingLimits {
  id: number;
  pipeline_id: number;
  pipeline_name: string;
  /** The pipeline's named inputs, for editing the values each run is given. */
  pipeline_inputs: PipelineInput[];
  weekday: number | null;
  day_of_month: number | null;
  /** The free text each run is given ("" when the pipeline has named inputs). */
  input: string;
  /** The value of each named input each run is given. */
  inputs: Record<string, string>;
  enabled: boolean;
  /** ISO 8601, UTC; null while the schedule is off. */
  next_run_at: string | null;
  last_run: ScheduleLastRun | null;
  /** Why its latest time could not start a run; null when it did. */
  last_error: string | null;
  created_at: string;
}

/** Body of POST /api/schedules: a pipeline, its timing and what each run is given. */
export interface ScheduleInput extends ScheduleTiming, PipelineRunRequest {
  pipeline_id: number;
  enabled?: boolean;
}

/**
 * Body of PATCH /api/schedules/<id>: omitted fields keep their value. `input` and `inputs`
 * replace what each run is given as a whole; so do the two limits (null removes one).
 */
export interface SchedulePatch extends Partial<ScheduleTiming>, PipelineRunRequest {
  enabled?: boolean;
}

export interface SchedulePreview {
  /** ISO 8601, UTC: when a schedule with this timing would run first. */
  next_run_at: string;
}
