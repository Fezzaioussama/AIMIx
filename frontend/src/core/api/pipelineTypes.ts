/** The pipeline definition: its steps, their flow and its inputs. Re-exported from `types.ts`. */

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
  /** What the run form starts with, e.g. the value the mission's request gave; may be missing. */
  default_value?: string;
}

export interface Pipeline {
  id?: number;
  name: string;
  /** Named run inputs; empty means the pipeline runs on one free-text input. */
  inputs: PipelineInput[];
  steps: PipelineStep[];
}
