import type { PipelineStep, StepResult } from '../../core/api/types';
import { groupByStage, outputOrders, type StageGroup } from './stages';

export type NodeStatus = 'pending' | 'running' | 'done';

export interface GraphNode {
  order: number;
  title: string;
  model: string;
  prompt: string;
  status: NodeStatus;
  /** Length of the step's output once it has run, for the node's summary line. */
  outputLength: number | null;
  isOutput: boolean;
}

/**
 * The diagram's view of a pipeline: its stages, each step's status taken from
 * the latest run. Kept pure so the component only draws (§2).
 */
export function buildGraph(
  steps: PipelineStep[],
  results: StepResult[],
  isRunning: boolean,
): StageGroup<GraphNode>[] {
  const outputs = new Map(results.map((result) => [result.step_order, result.output]));
  const deliverables = deliverableOrders(steps, results);
  const nodes = steps.map((step) => {
    const output = outputs.get(step.order);
    return {
      stage: step.stage,
      node: {
        order: step.order,
        title: step.title,
        model: step.model,
        prompt: step.prompt,
        status: nodeStatus(output, isRunning),
        outputLength: output === undefined ? null : output.length,
        isOutput: deliverables.has(step.order),
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
