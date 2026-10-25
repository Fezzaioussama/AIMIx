import type { PipelineStep, Run, RunApproval, RunStep, RunStepStatus } from '../../core/api/types';

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

export function runStep(order: number, status: RunStepStatus, output = ''): RunStep {
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
    input: 'topic',
    inputs: {},
    final_output: '',
    definition: { name: 'Launch kit', inputs: [], steps: DEFINITION_STEPS },
    steps: [
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'running'),
      runStep(3, 'pending'),
    ],
    pending_approvals: [],
    ...overrides,
  };
}

/** A request for the run's second step to send an email, with a minute to answer. */
export function makeApproval(overrides: Partial<RunApproval> = {}): RunApproval {
  return {
    id: 31,
    step_order: 2,
    tool_name: 'crm_send_email',
    tool_source: 'crm',
    tool_description: 'Send an email to a contact.',
    arguments: { to: 'ada@example.com', subject: 'Launch' },
    arguments_truncated: false,
    status: 'pending',
    created_at: '2026-10-24T10:00:00Z',
    expires_at: '2026-10-24T10:01:00Z',
    ...overrides,
  };
}

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}
