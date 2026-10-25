import type { PipelineStep, Run, RunStep, RunStepStatus, Usage } from '../../core/api/types';

/** Nothing used yet: what every run and step starts with. */
export const NO_USAGE: Usage = {
  input_tokens: 0,
  output_tokens: 0,
  cost_usd: null,
  cost_complete: true,
};

/** A usage of `input` tokens in and `output` out; its cost is known unless `cost` is null. */
export function usageOf(input: number, output: number, cost: number | null): Usage {
  return { input_tokens: input, output_tokens: output, cost_usd: cost, cost_complete: true };
}

/** What a step used: the tokens and cost columns of a run step. */
export type StepUsage = Pick<RunStep, 'input_tokens' | 'output_tokens' | 'cost_usd'>;

const NO_STEP_USAGE: StepUsage = { input_tokens: 0, output_tokens: 0, cost_usd: null };

/** Shared by the run tests: a three-step pipeline, stage 2 running two steps in parallel. */
function definitionStep(order: number, stage: number, title: string): PipelineStep {
  return {
    order,
    stage,
    title,
    is_output: order !== 1,
    expected_output: '',
    prompt: `${title} {input}`,
    model: 'vendor/writer',
    role: '',
    allowed_tools: null,
  };
}

const DEFINITION_STEPS = [
  definitionStep(1, 1, 'Research'),
  definitionStep(2, 2, 'Draft'),
  definitionStep(3, 2, 'Summary'),
];

export function runStep(
  order: number,
  status: RunStepStatus,
  output = '',
  used: StepUsage = NO_STEP_USAGE,
): RunStep {
  const source = DEFINITION_STEPS[order - 1];
  const started = status === 'pending' ? null : '2026-10-24T10:00:00Z';
  const finished = status === 'pending' || status === 'running' ? null : '2026-10-24T10:00:04Z';
  return {
    step_order: order,
    stage: source.stage,
    title: source.title,
    model: source.model,
    input_used: status === 'pending' ? '' : 'topic',
    output,
    is_output: source.is_output,
    tool_calls: status === 'succeeded' ? [{ name: 'calculator', status: 'success' }] : [],
    status,
    error:
      status === 'failed' ? { code: 'provider_timeout', detail: 'The agent timed out.' } : null,
    started_at: started,
    finished_at: finished,
    ...used,
  };
}

export function makeRun(overrides: Partial<Run> = {}): Run {
  return {
    id: 7,
    pipeline_id: 3,
    pipeline_name: 'Launch kit',
    status: 'running',
    error: null,
    created_at: '2026-10-24T10:00:00Z',
    started_at: '2026-10-24T10:00:00Z',
    finished_at: null,
    max_cost_usd: null,
    max_tokens: null,
    usage: NO_USAGE,
    input: 'topic',
    inputs: {},
    final_output: '',
    definition: { name: 'Launch kit', inputs: [], steps: DEFINITION_STEPS },
    steps: [
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'running'),
      runStep(3, 'pending'),
    ],
    ...overrides,
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
