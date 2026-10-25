import type {
  PipelineStep,
  RunStep,
  RunStepStatus,
  StepCondition,
  StepResult,
  StepReview,
} from '../../core/api/types';
import { groupByStage, outputOrders, type StageGroup } from './stages';
import { roundTotals } from './stepFlow';

/**
 * How the diagram shows a step. `pending` has not run (and will not, for now);
 * `waiting` is queued behind earlier stages of a run in progress; `skipped` did not
 * run because its condition did not hold.
 */
export type NodeStatus =
  | 'pending'
  | 'waiting'
  | 'running'
  | 'done'
  | 'failed'
  | 'stopped'
  | 'skipped';

export interface GraphNode {
  order: number;
  title: string;
  model: string;
  prompt: string;
  /** What the step must deliver, the node's summary until it has run. */
  expectedOutput: string;
  status: NodeStatus;
  /** Length of the step's output once it has run, for the node's summary line. */
  outputLength: number | null;
  isOutput: boolean;
  /** The step runs only while this holds. */
  condition: StepCondition | null;
  /** The step is a reviewer that can send the work back. */
  review: StepReview | null;
  /** The review round a followed run's step is in (1 for every other step), and the most
   * rounds its loop allows; null for a step outside any loop. */
  round: number;
  roundTotal: number | null;
}

const LIVE_STATUS: Record<RunStepStatus, NodeStatus> = {
  pending: 'waiting',
  running: 'running',
  succeeded: 'done',
  failed: 'failed',
  cancelled: 'stopped',
  skipped: 'skipped',
};

/** A run's step as the diagram shows it; a pending step waits only while its run is active. */
export function liveNodeStatus(step: RunStep, runActive: boolean): NodeStatus {
  return step.status === 'pending' && !runActive ? 'pending' : LIVE_STATUS[step.status];
}

/**
 * The diagram's view of a pipeline: its stages, each step's status taken from
 * the run shown — `liveSteps` when one is being followed — else from the latest
 * results. Kept pure so the component only draws (§2).
 */
export function buildGraph(
  steps: PipelineStep[],
  results: StepResult[],
  isRunning: boolean,
  liveSteps?: RunStep[],
): StageGroup<GraphNode>[] {
  const outputs = new Map(results.map((result) => [result.step_order, result.output]));
  const live = liveSteps && new Map(liveSteps.map((step) => [step.step_order, step]));
  // A followed run knows every step's verdict before its result exists.
  const deliverables = deliverableOrders(steps, liveSteps?.length ? liveSteps : results);
  const totals = roundTotals(steps);
  const nodes = steps.map((step) => {
    const output = outputs.get(step.order);
    const liveStep = live?.get(step.order);
    const status = liveStep ? liveNodeStatus(liveStep, isRunning) : nodeStatus(output, isRunning);
    return {
      stage: step.stage,
      node: {
        order: step.order,
        title: step.title,
        model: step.model,
        prompt: step.prompt,
        expectedOutput: step.expected_output,
        status,
        outputLength: output === undefined ? null : output.length,
        // A step that was skipped never counts as a deliverable.
        isOutput: deliverables.has(step.order) && status !== 'skipped',
        condition: step.condition,
        review: step.review,
        round: liveStep?.rounds ?? 1,
        roundTotal: totals.get(step.order) ?? null,
      },
    };
  });
  return groupByStage(nodes, (entry) => entry.stage).map((group) => ({
    stage: group.stage,
    items: group.items.map((entry) => entry.node),
  }));
}

/** After a run the backend's verdict wins; before one, predict it from the steps. */
function deliverableOrders(steps: PipelineStep[], results: StepResult[]): Set<number> {
  if (results.length === 0) return outputOrders(steps);
  return new Set(results.filter((result) => result.is_output).map((result) => result.step_order));
}

function nodeStatus(output: string | undefined, isRunning: boolean): NodeStatus {
  if (isRunning) return 'running';
  return output === undefined ? 'pending' : 'done';
}

/** What a click on the diagram points at: one step's output, or all outputs. */
export type OutputTarget = number | 'outputs';
