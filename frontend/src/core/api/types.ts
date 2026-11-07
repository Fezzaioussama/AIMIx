/**
 * Payload contracts shared by every feature (AGENTS.md §8: declared once,
 * imported — never redeclared per component).
 */

import type { PipelineInput, PipelineStep } from './pipelineTypes';

// Auth payloads (sign-in tokens, GET /api/protected) live in authTypes.ts.
export type { Account, AuthTokens, WhoAmI } from './authTypes';

// The pipeline definition (steps, their flow, inputs) lives in pipelineTypes.ts.
export type {
  AgentTool,
  ConditionOperator,
  Pipeline,
  PipelineInput,
  PipelineStep,
  StepCondition,
  StepReview,
} from './pipelineTypes';

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
  tool_calls: ToolCall[];
}

/** One tool call of a step: the tool, how it went, and what it was about. */
export interface ToolCall {
  name: string;
  status: 'success' | 'error';
  /** The query, the address, the path, the question; "" when the call has no subject. */
  target: string;
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
/** What a request asks: the OK for a tool call, or (ask_user) an answer to a question. */
export type ApprovalKind = 'approval' | 'question';

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
  /** The OK for a tool call, or (ask_user) an answer to a question. */
  kind: ApprovalKind;
  /** What you answered a question; empty otherwise. */
  answer: string;
  status: ApprovalStatus;
  created_at: string;
  /** Unanswered by then, the request expires and the tool does not act. */
  expires_at: string;
}

/** What started a run: its owner (by hand or through the API), a schedule, or the chat agent. */
export type RunTrigger = 'manual' | 'schedule' | 'chat' | 'webhook';

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
  /** What you thought of it once it ended; the planner's next team reads the note. */
  rating: RunRating;
  feedback: string;
}

/** What you thought of a run: useful (1), not useful (-1), or nothing yet (null). */
export type RunRating = 1 | -1 | null;

/** Body of PUT /api/runs/<id>/feedback. */
export interface RunFeedback {
  rating: RunRating;
  /** A note for the planner's next team; "" for none. */
  feedback: string;
}

/** A run's share link, which only its owner reads: anyone who opens `url` reads the report. */
export interface RunShare {
  token: string;
  url: string;
  created_at: string;
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

/** What the account spent today (UTC), and its allowance of the server's key. */
export interface DayUsage {
  spent: Usage;
  /** The bound while the account spends the server's key; null with a key of its own, or none. */
  max_cost_usd: number | null;
  max_tokens: number | null;
}

/** GET /api/usage: what the account's runs, chats and planning of the last `days` days used. */
export interface UsageReport {
  days: number;
  since: string;
  runs: number;
  /** Runs, chats and planning together. */
  usage: Usage;
  /** The chats and planning alone. */
  other: Usage;
  /** Costliest first. */
  pipelines: PipelineUsage[];
  today: DayUsage;
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
  /** Where its OAuth sign-in stands: none, started, or connected (its tools use the token). */
  oauth: IntegrationOAuth;
}

export type IntegrationOAuth = '' | 'pending' | 'connected';

/** POST /api/integrations/<id>/oauth: the page the browser opens to sign in. */
export interface OAuthStart {
  authorization_url: string;
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
