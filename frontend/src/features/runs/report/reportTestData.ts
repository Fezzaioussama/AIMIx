/**
 * Runs for the report's tests, beside `makeRun` in ../testData: teams with a reviewer whose
 * VERDICT can send the work back, and steps in any state.
 */
import type { PipelineStep, Run, RunStep, RunStepStatus } from '../../../core/api/types';
import { makeRun, runStep } from '../testData';

/** A step of a definition: no output, no role, every tool, unless `fields` says otherwise. */
export function defined(
  order: number,
  stage: number,
  title: string,
  fields: Partial<PipelineStep> = {},
): PipelineStep {
  return {
    order,
    stage,
    title,
    is_output: false,
    expected_output: '',
    prompt: `${title} {input}`,
    model: 'vendor/writer',
    role: '',
    allowed_tools: null,
    condition: null,
    review: null,
    ...fields,
  };
}

/** The run row of `definition` in `status`: the shape of `runStep`, its output its title's. */
export function stepFrom(
  definition: PipelineStep,
  status: RunStepStatus,
  fields: Partial<RunStep> = {},
): RunStep {
  return {
    ...runStep(1, status, status === 'succeeded' ? `${definition.title} text` : ''),
    step_order: definition.order,
    stage: definition.stage,
    title: definition.title,
    is_output: definition.is_output,
    ...fields,
  };
}

/** One step's state in a run: its status, and any fields that differ (rounds, verdict, …). */
export type StepState = [RunStepStatus, Partial<RunStep>?];

/** A run of `definition`, its steps in `states` (in the definition's order). */
export function runOf(
  definition: PipelineStep[],
  states: StepState[],
  overrides: Partial<Run> = {},
): Run {
  return makeRun({
    definition: { name: 'Launch', inputs: [], steps: definition },
    steps: states.map(([status, fields], index) => stepFrom(definition[index], status, fields)),
    ...overrides,
  });
}

/**
 * What the planner makes: Research, then two writers at the same time, then the
 * Orchestrator's final check, which may send the work back to the writers twice.
 */
export const TEAM: PipelineStep[] = [
  defined(1, 1, 'Research', { role: 'Researcher' }),
  defined(2, 2, 'Blog post', { role: 'Writer', is_output: true }),
  defined(3, 2, 'LinkedIn post', { role: 'Writer', is_output: true }),
  defined(4, 3, 'Final check', {
    role: 'Orchestrator',
    review: { send_back_to_stage: 2, max_rounds: 2 },
  }),
];

export function teamRun(states: StepState[], overrides: Partial<Run> = {}): Run {
  return runOf(TEAM, states, overrides);
}

/**
 * research (1) -> writer (2) -> QA (3, sends the work back to 2) -> SEO (4, only for blogs),
 * the pipeline LiveRunFlow's tests used.
 */
export const FLOW: PipelineStep[] = [
  defined(1, 1, 'Research'),
  defined(2, 2, 'Writer', { is_output: true }),
  defined(3, 3, 'QA', { review: { send_back_to_stage: 2, max_rounds: 2 } }),
  defined(4, 4, 'SEO', {
    is_output: true,
    condition: { source: 'previous_output', operator: 'contains', value: 'blog' },
  }),
];

export function flowRun(states: StepState[], overrides: Partial<Run> = {}): Run {
  return runOf(FLOW, states, overrides);
}

/** The run's step `order`; a test that asks for one the run lacks fails. */
export function stepOf(run: Run, order: number): RunStep {
  const step = run.steps.find((item) => item.step_order === order);
  if (step === undefined) throw new Error(`The run has no step ${order}.`);
  return step;
}

/** A finished run: when it ended, 4 min 54 s after it started. */
export const ENDED = { finished_at: '2026-10-24T10:04:54Z' } as const;
