import type { Pipeline, PipelineStep, Run, RunStatus } from '../../core/api/types';

/**
 * What a run's status means for the screens. Mirrors ACTIVE_RUN_STATUSES and
 * RESUMABLE_RUN_STATUSES in backend/api/models.py, which decide for real.
 */
const ACTIVE: ReadonlySet<RunStatus> = new Set<RunStatus>(['queued', 'running', 'waiting']);
const RESUMABLE: ReadonlySet<RunStatus> = new Set<RunStatus>([
  'failed',
  'cancelled',
  'interrupted',
]);

/** Queued, running or waiting for an approval: it can be stopped, and is worth polling. */
export function isActive(status: RunStatus): boolean {
  return ACTIVE.has(status);
}

/** Stopped before the end: it can continue from its first unfinished stage. */
export function isResumable(status: RunStatus): boolean {
  return RESUMABLE.has(status);
}

/** Steps that are done with: finished, or skipped because their condition did not hold. */
export function finishedStepCount(run: Run): number {
  return run.steps.filter((step) => step.status === 'succeeded' || step.status === 'skipped')
    .length;
}

/** The fields that decide what a step does, in a stable order. */
function stepShape(step: PipelineStep) {
  return [
    step.order,
    step.stage,
    step.title,
    step.prompt,
    step.model,
    step.role,
    step.allowed_tools,
    step.is_output,
    step.expected_output,
    step.condition,
    step.review,
  ];
}

/** Whether the run executed exactly this version of the pipeline. */
export function ranThisVersion(run: Run, pipeline: Pipeline): boolean {
  const shape = (inputs: Pipeline['inputs'], steps: PipelineStep[]) =>
    JSON.stringify([inputs.map((field) => field.name), steps.map(stepShape)]);
  return (
    run.pipeline_id === pipeline.id &&
    shape(run.definition.inputs, run.definition.steps) === shape(pipeline.inputs, pipeline.steps)
  );
}
