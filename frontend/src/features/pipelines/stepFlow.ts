import type {
  ConditionOperator,
  PipelineInput,
  PipelineStep,
  StepCondition,
  StepReview,
} from '../../core/api/types';
import { PREVIOUS_OUTPUT, inputNameOf, inputSource, stepOrderOf, stepSource } from './flowSources';
import { inputLabel } from './pipelineInputs';

/**
 * Conditional steps and review loops as the editor and the diagram see them. The rules
 * mirror backend/api/services/multiagent/conditions.py and reviews.py, which decide for
 * real; here they only help people choose and show what is wrong before a save.
 */

/** Longest text a condition compares with, and the most times work may be sent back. */
export const CONDITION_VALUE_MAX_LENGTH = 200;
export const REVIEW_MAX_ROUNDS = 5;
export const DEFAULT_REVIEW_ROUNDS = 2;

export interface OperatorOption {
  value: ConditionOperator;
  label: string;
  /** Whether it compares with text; `is empty` and `is not empty` do not. */
  takesValue: boolean;
}

/** Every comparison a condition can make, in the words the editor shows (a registry). */
export const CONDITION_OPERATORS: readonly OperatorOption[] = [
  { value: 'contains', label: 'contains', takesValue: true },
  { value: 'not_contains', label: 'does not contain', takesValue: true },
  { value: 'equals', label: 'is exactly', takesValue: true },
  { value: 'not_equals', label: 'is not exactly', takesValue: true },
  { value: 'is_empty', label: 'is empty', takesValue: false },
  { value: 'not_empty', label: 'is not empty', takesValue: false },
];

export function operatorOption(operator: string): OperatorOption | undefined {
  return CONDITION_OPERATORS.find((option) => option.value === operator);
}

/** The steps that run in a stage before this step's, in the order they run. */
export function earlierSteps(step: PipelineStep, steps: PipelineStep[]): PipelineStep[] {
  return steps
    .filter((other) => other.stage < step.stage)
    .sort((a, b) => a.stage - b.stage || a.order - b.order);
}

/** The stages before this step's that have steps, ascending: where a reviewer may send work. */
export function earlierStages(step: PipelineStep, steps: PipelineStep[]): number[] {
  return [...new Set(earlierSteps(step, steps).map((other) => other.stage))];
}

export interface SourceOption {
  value: string;
  label: string;
}

function resultOf(step: PipelineStep): string {
  return step.title.trim() ? `“${step.title.trim()}” (step ${step.order})` : `step ${step.order}`;
}

/** What this step's condition may look at: the previous result, each input, each earlier step. */
export function conditionSources(
  step: PipelineStep,
  steps: PipelineStep[],
  inputs: PipelineInput[],
): SourceOption[] {
  const earlier = earlierSteps(step, steps);
  return [
    {
      value: PREVIOUS_OUTPUT,
      label: earlier.length === 0 ? 'The text you start with' : 'The previous stage’s result',
    },
    ...inputs.map((field) => ({
      value: inputSource(field.name),
      label: `Input: ${inputLabel(field)}`,
    })),
    ...earlier.map((other) => ({
      value: stepSource(other.order),
      label: `Result of ${resultOf(other)}`,
    })),
  ];
}

/** What a new condition starts as: the previous result "contains" nothing yet. */
export function newCondition(): StepCondition {
  return { source: PREVIOUS_OUTPUT, operator: 'contains', value: '' };
}

/** A new review sends the work to the stage right before this step's, twice at most. */
export function newReview(step: PipelineStep, steps: PipelineStep[]): StepReview {
  const stages = earlierStages(step, steps);
  return {
    send_back_to_stage: stages[stages.length - 1] ?? 1,
    max_rounds: DEFAULT_REVIEW_ROUNDS,
  };
}

/** "1 time", "2 times". */
export function timesWords(count: number): string {
  return count === 1 ? '1 time' : `${count} times`;
}

/** What a condition looks at, in words: "the previous result", "the input “Topic”". */
function subjectOf(
  source: string,
  step: PipelineStep,
  steps: PipelineStep[],
  inputs: PipelineInput[],
): string {
  if (source === PREVIOUS_OUTPUT) {
    return earlierSteps(step, steps).length === 0
      ? 'the text the run starts with'
      : 'the previous result';
  }
  const name = inputNameOf(source);
  if (name !== null) {
    const field = inputs.find((candidate) => candidate.name === name);
    return `the input “${field ? inputLabel(field) : name}”`;
  }
  const order = stepOrderOf(source);
  const looked = steps.find((candidate) => candidate.order === order);
  if (looked) return `the result of ${resultOf(looked)}`;
  return order === 0 ? 'a step that was removed' : 'something that is not there';
}

/** A step's condition in words, e.g. `the previous result contains “blog”`; null without one. */
export function describeCondition(
  step: PipelineStep,
  steps: PipelineStep[],
  inputs: PipelineInput[] = [],
): string | null {
  const { condition } = step;
  if (condition === null) return null;
  const operator = operatorOption(condition.operator);
  const compared = operator?.takesValue === false ? '' : ` “${condition.value.trim()}”`;
  const subject = subjectOf(condition.source, step, steps, inputs);
  return `${subject} ${operator?.label ?? condition.operator}${compared}`;
}

/** A review in words: "Sends the work back to stage 2, up to 2 times". */
export function describeReview(review: StepReview): string {
  return `Sends the work back to stage ${review.send_back_to_stage}, up to ${timesWords(review.max_rounds)}`;
}

/** The stages one reviewer's loop covers, by stage number. */
export interface ReviewLoop {
  /** The reviewer's step order. */
  reviewer: number;
  first: number;
  last: number;
  maxRounds: number;
}

export function loopsOverlap(a: ReviewLoop, b: ReviewLoop): boolean {
  return a.first <= b.last && b.first <= a.last;
}

/** The loop a step with a review makes, when it can work; null for any other step. */
export function loopOf(step: PipelineStep, steps: PipelineStep[]): ReviewLoop | null {
  const { review } = step;
  if (review === null) return null;
  const works =
    review.send_back_to_stage < step.stage &&
    steps.some((other) => other.stage === review.send_back_to_stage) &&
    review.max_rounds >= 1 &&
    review.max_rounds <= REVIEW_MAX_ROUNDS;
  if (!works) return null;
  return {
    reviewer: step.order,
    first: review.send_back_to_stage,
    last: step.stage,
    maxRounds: review.max_rounds,
  };
}

/**
 * The loops a run follows: those that can work, and of loops that share a stage only the
 * one that starts first (the engine drops the others, and saving refuses them).
 */
export function reviewLoops(steps: PipelineStep[]): ReviewLoop[] {
  const usable = steps
    .map((step) => loopOf(step, steps))
    .filter((loop): loop is ReviewLoop => loop !== null)
    .sort((a, b) => a.first - b.first || a.last - b.last || a.reviewer - b.reviewer);
  const kept: ReviewLoop[] = [];
  for (const loop of usable) {
    if (!kept.some((other) => loopsOverlap(loop, other))) kept.push(loop);
  }
  return kept;
}

/** For each step in a loop's stages, how many times it runs at most: `1 + max_rounds`. */
export function roundTotals(steps: PipelineStep[]): Map<number, number> {
  const totals = new Map<number, number>();
  for (const loop of reviewLoops(steps)) {
    for (const step of steps) {
      if (step.stage >= loop.first && step.stage <= loop.last)
        totals.set(step.order, 1 + loop.maxRounds);
    }
  }
  return totals;
}
