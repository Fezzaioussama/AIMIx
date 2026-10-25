import { describe, expect, it } from 'vitest';

import type { PipelineStep, StepCondition, StepReview } from '../../core/api/types';
import { followNewStage, followRenumbering, withoutStep } from './stepFlowEdits';

function step(
  order: number,
  stage: number,
  flow: { condition?: StepCondition; review?: StepReview } = {},
): PipelineStep {
  return {
    order,
    stage,
    title: `T${order}`,
    is_output: false,
    expected_output: '',
    prompt: 'p',
    model: 'v/m',
    role: '',
    allowed_tools: null,
    condition: flow.condition ?? null,
    review: flow.review ?? null,
  };
}

const looks = (order: number): StepCondition => ({
  source: `step:${order}`,
  operator: 'not_empty',
  value: '',
});

const sources = (steps: PipelineStep[]) => steps.map((item) => item.condition?.source ?? null);

describe('withoutStep', () => {
  it('numbers the steps that are left from 1 again', () => {
    const steps = withoutStep([step(1, 1), step(2, 2), step(3, 3)], 2);
    expect(steps.map((item) => [item.order, item.title])).toEqual([
      [1, 'T1'],
      [2, 'T3'],
    ]);
  });

  it('keeps a condition on the step it looked at, under that step’s new number', () => {
    // Step 3 looks at step 2; step 1 goes, so both move up one.
    const steps = withoutStep([step(1, 1), step(2, 2), step(3, 3, { condition: looks(2) })], 1);
    expect(steps.map((item) => item.title)).toEqual(['T2', 'T3']);
    expect(sources(steps)).toEqual([null, 'step:1']);
  });

  it('never moves a condition onto another step', () => {
    // Step 4 looks at step 3. Removing step 2 makes old step 3 the new step 2.
    const steps = withoutStep(
      [step(1, 1), step(2, 2), step(3, 3), step(4, 4, { condition: looks(3) })],
      2,
    );
    expect(sources(steps)).toEqual([null, null, 'step:2']);
    expect(steps[1].title).toBe('T3');
  });

  it('leaves a condition whose step was removed looking at a step that does not exist', () => {
    const steps = withoutStep([step(1, 1), step(2, 2), step(3, 3, { condition: looks(2) })], 2);
    expect(sources(steps)).toEqual([null, 'step:0']);
  });

  it('does not touch conditions that look at an input or the previous result', () => {
    const input: StepCondition = { source: 'input:topic', operator: 'equals', value: 'x' };
    const previous: StepCondition = { source: 'previous_output', operator: 'is_empty', value: '' };
    const steps = withoutStep(
      [step(1, 1), step(2, 2, { condition: input }), step(3, 3, { condition: previous })],
      1,
    );
    expect(sources(steps)).toEqual(['input:topic', 'previous_output']);
  });

  it('keeps a review as it is, for the editor to say if it no longer works', () => {
    const review = { send_back_to_stage: 2, max_rounds: 2 };
    const steps = withoutStep([step(1, 1), step(2, 2), step(3, 3, { review })], 2);
    expect(steps[1].review).toEqual(review);
  });

  it('changes nothing for a number no step has', () => {
    const before = [step(1, 1), step(2, 2, { condition: looks(1) })];
    const after = withoutStep(before, 9);
    expect(after).toEqual(before);
  });
});

describe('followRenumbering', () => {
  it('follows each condition to its step’s new number', () => {
    const steps = [step(1, 1), step(2, 2, { condition: looks(1) })];
    const numbers = new Map<number, number | null>([
      [1, 3],
      [2, 4],
    ]);
    expect(sources(followRenumbering(steps, numbers))).toEqual([null, 'step:3']);
  });

  it('leaves a condition that looks at a step it has no new number for', () => {
    const steps = [step(2, 2, { condition: looks(7) })];
    expect(sources(followRenumbering(steps, new Map([[1, 1]])))).toEqual(['step:7']);
  });

  it('returns the same step object when nothing changes', () => {
    const steps = [step(1, 1), step(2, 2, { condition: looks(1) })];
    const followed = followRenumbering(steps, new Map<number, number | null>([[1, 1]]));
    expect(followed[0]).toBe(steps[0]);
  });
});

describe('followNewStage', () => {
  it('moves the target of a review that went past the new stage', () => {
    const steps = [
      step(1, 1),
      step(2, 3, { review: { send_back_to_stage: 2, max_rounds: 1 } }),
      step(3, 4, { review: { send_back_to_stage: 1, max_rounds: 1 } }),
    ];
    // A stage was opened right after stage 1.
    const followed = followNewStage(steps, 1);
    expect(followed[1].review?.send_back_to_stage).toBe(3);
    // A review that goes back to the stage the new one came after keeps it.
    expect(followed[2].review?.send_back_to_stage).toBe(1);
  });

  it('leaves steps without a review alone', () => {
    const steps = [step(1, 1), step(2, 2)];
    expect(followNewStage(steps, 1)).toEqual(steps);
  });
});
