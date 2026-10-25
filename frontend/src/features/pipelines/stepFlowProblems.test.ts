import { describe, expect, it } from 'vitest';

import type { PipelineInput, PipelineStep, StepCondition, StepReview } from '../../core/api/types';
import { CONDITION_VALUE_MAX_LENGTH } from './stepFlow';
import { conditionProblem, reviewProblem } from './stepFlowProblems';

function step(
  order: number,
  stage: number,
  flow: { condition?: StepCondition; review?: StepReview } = {},
): PipelineStep {
  return {
    order,
    stage,
    title: '',
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

const when = (source: string, operator: StepCondition['operator'], value = ''): StepCondition => ({
  source,
  operator,
  value,
});

const TOPIC: PipelineInput = { name: 'topic', label: 'Topic', description: '' };

/** A pipeline of three stages; the step under test is step 3, in stage 3. */
function problemWith(condition: StepCondition | null, inputs: PipelineInput[] = [TOPIC]) {
  const steps = [step(1, 1), step(2, 2), step(3, 3), step(4, 3)];
  const own = { ...steps[2], condition };
  return conditionProblem(own, [steps[0], steps[1], own, steps[3]], inputs);
}

describe('conditionProblem', () => {
  it('is null for no condition, and for one that can work', () => {
    expect(problemWith(null)).toBeNull();
    expect(problemWith(when('previous_output', 'contains', 'blog'))).toBeNull();
    expect(problemWith(when('input:topic', 'equals', 'bees'))).toBeNull();
    expect(problemWith(when('step:1', 'not_empty'))).toBeNull();
    expect(problemWith(when('step:2', 'is_empty', 'ignored'))).toBeNull();
  });

  it('needs text to compare with, unless the comparison takes none', () => {
    expect(problemWith(when('previous_output', 'contains', '   '))).toBe(
      'Enter the text to compare with.',
    );
    expect(problemWith(when('previous_output', 'equals'))).toBe('Enter the text to compare with.');
    expect(problemWith(when('previous_output', 'is_empty'))).toBeNull();
  });

  it('accepts text up to the limit, measured without surrounding spaces', () => {
    const text = 'x'.repeat(CONDITION_VALUE_MAX_LENGTH);
    expect(problemWith(when('previous_output', 'contains', ` ${text} `))).toBeNull();
    expect(problemWith(when('previous_output', 'contains', `${text}x`))).toBe(
      `The text can have at most ${CONDITION_VALUE_MAX_LENGTH} characters.`,
    );
  });

  it('names a comparison it does not know', () => {
    const odd = { source: 'previous_output', operator: 'sounds_like' as never, value: 'x' };
    expect(problemWith(odd)).toBe('This condition compares in a way AIMIx does not know.');
  });

  it('refuses something to look at that is not one of the three kinds', () => {
    expect(problemWith(when('weather:today', 'contains', 'x'))).toBe(
      'Choose what the condition looks at.',
    );
    expect(problemWith(when('', 'contains', 'x'))).toBe('Choose what the condition looks at.');
    expect(problemWith(when('previous_output:1', 'contains', 'x'))).toBe(
      'Choose what the condition looks at.',
    );
  });

  it('refuses an input the pipeline no longer has', () => {
    expect(problemWith(when('input:audience', 'contains', 'x'))).toBe(
      'The input “audience” no longer exists. Choose what the condition looks at again.',
    );
    expect(problemWith(when('input:topic', 'contains', 'x'), [])).toContain('no longer exists');
  });

  it('refuses a step that does not run before it', () => {
    const later = problemWith(when('step:4', 'contains', 'x'));
    expect(later).toBe(
      'Step 4 no longer runs before this step, so its result is not available here. Choose again.',
    );
    expect(problemWith(when('step:3', 'contains', 'x'))).toContain('Step 3 no longer runs before');
    expect(problemWith(when('step:9', 'contains', 'x'))).toContain('Step 9 no longer runs before');
  });

  it('says so when the step it looked at was removed', () => {
    expect(problemWith(when('step:0', 'contains', 'x'))).toBe(
      'The step this condition looked at was removed. Choose again.',
    );
    expect(problemWith(when('step:one', 'contains', 'x'))).toBe(
      'Choose what the condition looks at.',
    );
  });
});

function reviewer(config: StepReview | null, stage = 3) {
  const steps = [step(1, 1), step(2, 2), step(3, stage, { review: config ?? undefined })];
  return reviewProblem(steps[2], steps);
}

describe('reviewProblem', () => {
  it('is null for no review, and for one that can work', () => {
    expect(reviewer(null)).toBeNull();
    expect(reviewer({ send_back_to_stage: 2, max_rounds: 2 })).toBeNull();
    expect(reviewer({ send_back_to_stage: 1, max_rounds: 5 })).toBeNull();
  });

  it('allows one to five times only', () => {
    expect(reviewer({ send_back_to_stage: 2, max_rounds: 0 })).toBe('Choose from 1 to 5 times.');
    expect(reviewer({ send_back_to_stage: 2, max_rounds: 6 })).toBe('Choose from 1 to 5 times.');
  });

  it('needs an earlier stage that has steps', () => {
    const where = 'Choose where to send the work again.';
    expect(reviewer({ send_back_to_stage: 3, max_rounds: 1 })).toBe(
      `Stage 3 is not an earlier stage with steps. ${where}`,
    );
    expect(reviewer({ send_back_to_stage: 9, max_rounds: 1 })).toContain('Stage 9 is not');
    expect(reviewer({ send_back_to_stage: 0, max_rounds: 1 })).toContain('Stage 0 is not');
  });

  it('refuses a reviewer that has no earlier stage at all', () => {
    expect(reviewer({ send_back_to_stage: 1, max_rounds: 1 }, 1)).toContain('Stage 1 is not');
  });

  it('refuses a loop that shares a stage with another and names that one', () => {
    const steps = [
      step(1, 1),
      step(2, 2),
      step(3, 3, { review: { send_back_to_stage: 2, max_rounds: 1 } }),
      step(4, 4, { review: { send_back_to_stage: 1, max_rounds: 1 } }),
    ];
    expect(reviewProblem(steps[2], steps)).toBe(
      'This loop shares stages with the loop of step 4. Review loops cannot overlap.',
    );
    // The loop that starts first is the one that stands.
    expect(reviewProblem(steps[3], steps)).toBeNull();
  });
});
