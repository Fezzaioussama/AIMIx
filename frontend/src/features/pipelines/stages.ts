import type { PipelineStep } from '../../core/api/types';
import { followNewStage, followRenumbering } from './stepFlowEdits';

export interface StageGroup<T> {
  stage: number;
  items: T[];
}

/**
 * Group items into execution stages, ascending. Items keep their relative order
 * within a stage. Shared by the step editors and the run results so both show
 * the same grouping the backend executes.
 */
export function groupByStage<T>(items: T[], stageOf: (item: T) => number): StageGroup<T>[] {
  const groups = new Map<number, T[]>();
  for (const item of items) {
    const stage = stageOf(item);
    groups.set(stage, [...(groups.get(stage) ?? []), item]);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a - b)
    .map(([stage, grouped]) => ({ stage, items: grouped }));
}

/** The stage a newly added step gets: after every existing one, i.e. sequential. */
export function nextStage(steps: { stage: number }[]): number {
  return steps.reduce((highest, step) => Math.max(highest, step.stage), 0) + 1;
}

/** Insert a step beside a stage or in a new stage immediately after it. */
interface InsertStepOptions {
  model: string;
  stage: number;
  parallel: boolean;
  isOutput?: boolean;
}

export function insertStep(steps: PipelineStep[], options: InsertStepOptions): PipelineStep[] {
  const { model, stage, parallel, isOutput = false } = options;
  const updated = parallel
    ? steps
    : followNewStage(steps, stage).map((step) => ({
        ...step,
        stage: step.stage > stage ? step.stage + 1 : step.stage,
      }));
  const sorted = [
    ...updated,
    {
      order: Math.max(0, ...steps.map((step) => step.order)) + 1,
      stage: parallel ? stage : stage + 1,
      title: '',
      is_output: isOutput,
      expected_output: '',
      prompt: '',
      model,
      role: '',
      allowed_tools: null,
      condition: null,
      review: null,
    },
  ].sort((first, second) => first.stage - second.stage || first.order - second.order);
  // Numbering the steps again moves them: what refers to a step by number follows it.
  const numbers = new Map<number, number | null>(
    sorted.map((step, index) => [step.order, index + 1]),
  );
  return followRenumbering(
    sorted.map((step, index) => ({ ...step, order: index + 1 })),
    numbers,
  );
}

/**
 * Steps that are the pipeline's outputs, for previews before a run. Mirrors
 * `output_orders` in backend/api/services/pipelines.py, which decides for real
 * runs (run results carry `is_output`): marked steps, else the last stage.
 */
export function outputOrders(steps: { order: number; stage: number; is_output: boolean }[]) {
  const marked = steps.filter((step) => step.is_output);
  if (marked.length > 0) return new Set(marked.map((step) => step.order));
  const lastStage = Math.max(0, ...steps.map((step) => step.stage));
  return new Set(steps.filter((step) => step.stage === lastStage).map((step) => step.order));
}

/** A step's display name: its title, or its position when it has none. */
export function stepLabel(step: { order: number; title: string }): string {
  return step.title.trim() || `Step ${step.order}`;
}
