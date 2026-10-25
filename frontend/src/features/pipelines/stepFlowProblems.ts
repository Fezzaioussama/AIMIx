import type { PipelineInput, PipelineStep } from '../../core/api/types';
import { parseSource, stepOrderOf } from './flowSources';
import {
  CONDITION_VALUE_MAX_LENGTH,
  REVIEW_MAX_ROUNDS,
  earlierStages,
  earlierSteps,
  loopOf,
  loopsOverlap,
  operatorOption,
  reviewLoops,
} from './stepFlow';

/**
 * What stops a step's condition or review from working, in plain words for the editor.
 * Mirrors the checks a save makes (backend/api/services/pipeline_flow.py), which decide
 * for real; here they tell the person why a save would be refused.
 */

const CHOOSE_AGAIN = 'Choose what the condition looks at.';

type SourceCheck = (
  key: string,
  step: PipelineStep,
  steps: PipelineStep[],
  inputs: PipelineInput[],
) => string | null;

function inputProblem(
  key: string,
  _step: PipelineStep,
  _steps: PipelineStep[],
  inputs: PipelineInput[],
): string | null {
  return inputs.some((field) => field.name === key)
    ? null
    : `The input “${key}” no longer exists. Choose what the condition looks at again.`;
}

function stepProblem(key: string, step: PipelineStep, steps: PipelineStep[]): string | null {
  const order = stepOrderOf(`step:${key}`);
  if (order === null) return CHOOSE_AGAIN;
  if (order === 0) return 'The step this condition looked at was removed. Choose again.';
  if (earlierSteps(step, steps).some((other) => other.order === order)) return null;
  return `Step ${order} no longer runs before this step, so its result is not available here. Choose again.`;
}

/** Each kind of source and how it is checked (a registry, like the engine's). */
const SOURCE_CHECKS: Record<string, SourceCheck> = {
  previous_output: (key) => (key === '' ? null : CHOOSE_AGAIN),
  input: inputProblem,
  step: stepProblem,
};

/** Why this step's condition cannot work, or null when it can (or there is none). */
export function conditionProblem(
  step: PipelineStep,
  steps: PipelineStep[],
  inputs: PipelineInput[],
): string | null {
  const { condition } = step;
  if (condition === null) return null;
  const operator = operatorOption(condition.operator);
  if (operator === undefined) return 'This condition compares in a way AIMIx does not know.';
  const { kind, key } = parseSource(condition.source);
  const check = Object.hasOwn(SOURCE_CHECKS, kind) ? SOURCE_CHECKS[kind] : undefined;
  const source = check === undefined ? CHOOSE_AGAIN : check(key, step, steps, inputs);
  if (source !== null) return source;
  const value = condition.value.trim();
  if (operator.takesValue && value === '') return 'Enter the text to compare with.';
  if (value.length > CONDITION_VALUE_MAX_LENGTH) {
    return `The text can have at most ${CONDITION_VALUE_MAX_LENGTH} characters.`;
  }
  return null;
}

/** Why this step's review loop cannot work, or null when it can (or there is none). */
export function reviewProblem(step: PipelineStep, steps: PipelineStep[]): string | null {
  const { review } = step;
  if (review === null) return null;
  if (review.max_rounds < 1 || review.max_rounds > REVIEW_MAX_ROUNDS) {
    return `Choose from 1 to ${REVIEW_MAX_ROUNDS} times.`;
  }
  if (!earlierStages(step, steps).includes(review.send_back_to_stage)) {
    return `Stage ${review.send_back_to_stage} is not an earlier stage with steps. Choose where to send the work again.`;
  }
  const own = loopOf(step, steps);
  const kept = reviewLoops(steps);
  if (own === null || kept.some((loop) => loop.reviewer === own.reviewer)) return null;
  const other = kept.find((loop) => loopsOverlap(own, loop));
  return `This loop shares stages with the loop of step ${other?.reviewer}. Review loops cannot overlap.`;
}
