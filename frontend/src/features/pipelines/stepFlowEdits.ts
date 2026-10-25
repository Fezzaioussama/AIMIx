import type { PipelineStep } from '../../core/api/types';
import { REMOVED_STEP_SOURCE, stepOrderOf, stepSource } from './flowSources';

/**
 * Editing steps renumbers them, and conditions and review loops refer to steps by number
 * and to stages by number. These keep every such reference pointing at what it did:
 * a reference is never silently moved onto another step, and never silently removed (a
 * condition that lost its step is left looking at nothing, and the editor says so).
 */

/**
 * `steps` once the steps were renumbered: each condition that looks at a step follows it
 * to its new number (`numbers`: old order → new order). One that looked at a step that is
 * gone (`null`) is left looking at a step that does not exist, for the person to choose again.
 */
export function followRenumbering(
  steps: PipelineStep[],
  numbers: ReadonlyMap<number, number | null>,
): PipelineStep[] {
  return steps.map((step) => {
    const looked = step.condition === null ? null : stepOrderOf(step.condition.source);
    if (step.condition === null || looked === null || !numbers.has(looked)) return step;
    const now = numbers.get(looked) ?? null;
    const source = now === null ? REMOVED_STEP_SOURCE : stepSource(now);
    return { ...step, condition: { ...step.condition, source } };
  });
}

/**
 * `steps` without the one numbered `order`; the rest are numbered from 1 again in their
 * order, and the conditions that looked at them follow.
 */
export function withoutStep(steps: PipelineStep[], order: number): PipelineStep[] {
  const kept = steps.filter((step) => step.order !== order);
  const numbers = new Map<number, number | null>([[order, null]]);
  kept.forEach((step, index) => numbers.set(step.order, index + 1));
  return followRenumbering(
    kept.map((step, index) => ({ ...step, order: index + 1 })),
    numbers,
  );
}

/**
 * A stage was opened right after `stage`, pushing every later stage up by one: review
 * loops that send work back past it follow the stage they meant.
 */
export function followNewStage(steps: PipelineStep[], stage: number): PipelineStep[] {
  return steps.map((step) =>
    step.review !== null && step.review.send_back_to_stage > stage
      ? {
          ...step,
          review: { ...step.review, send_back_to_stage: step.review.send_back_to_stage + 1 },
        }
      : step,
  );
}
