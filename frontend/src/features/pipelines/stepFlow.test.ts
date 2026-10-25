import { describe, expect, it } from 'vitest';

import type { PipelineInput, PipelineStep, StepCondition, StepReview } from '../../core/api/types';
import {
  CONDITION_OPERATORS,
  DEFAULT_REVIEW_ROUNDS,
  conditionSources,
  describeCondition,
  describeReview,
  earlierStages,
  earlierSteps,
  loopOf,
  newCondition,
  newReview,
  operatorOption,
  reviewLoops,
  roundTotals,
  timesWords,
} from './stepFlow';

function step(
  order: number,
  stage: number,
  title = '',
  flow: { condition?: StepCondition; review?: StepReview } = {},
): PipelineStep {
  return {
    order,
    stage,
    title,
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

const review = (stage: number, rounds = 2): StepReview => ({
  send_back_to_stage: stage,
  max_rounds: rounds,
});

const TOPIC: PipelineInput = { name: 'topic', label: 'Topic', description: '' };
const AUDIENCE: PipelineInput = { name: 'audience', label: '', description: '' };

describe('the steps before a step', () => {
  const steps = [step(3, 3), step(1, 1), step(2, 2), step(4, 2), step(5, 3)];

  it('are the steps of earlier stages, in the order they run', () => {
    const [, , , , last] = steps;
    expect(earlierSteps(last, steps).map((item) => item.order)).toEqual([1, 2, 4]);
  });

  it('leave out steps of the same stage and of later ones', () => {
    expect(earlierSteps(step(9, 1), steps)).toEqual([]);
  });

  it('give the stages a reviewer may send work to, once each', () => {
    expect(earlierStages(step(9, 3), steps)).toEqual([1, 2]);
    expect(earlierStages(step(9, 1), steps)).toEqual([]);
  });

  it('skip a stage number nothing runs in', () => {
    expect(earlierStages(step(9, 6), [step(1, 1), step(2, 4)])).toEqual([1, 4]);
  });
});

describe('conditionSources', () => {
  const steps = [step(1, 1, 'Research'), step(2, 2, ''), step(3, 3, 'Publish'), step(4, 3, 'Alt')];

  it('offers the previous result, each input and each earlier step', () => {
    expect(conditionSources(steps[2], steps, [TOPIC, AUDIENCE])).toEqual([
      { value: 'previous_output', label: 'The previous stage’s result' },
      { value: 'input:topic', label: 'Input: Topic' },
      { value: 'input:audience', label: 'Input: audience' },
      { value: 'step:1', label: 'Result of “Research” (step 1)' },
      { value: 'step:2', label: 'Result of step 2' },
    ]);
  });

  it('calls the previous result the text you start with in the first stage', () => {
    const [first] = conditionSources(steps[0], steps, []);
    expect(first).toEqual({ value: 'previous_output', label: 'The text you start with' });
  });

  it('never offers a step that does not run before it', () => {
    const values = conditionSources(steps[1], steps, []).map((option) => option.value);
    expect(values).toEqual(['previous_output', 'step:1']);
  });
});

describe('describeCondition', () => {
  const steps = [step(1, 1, 'Research'), step(2, 2, 'SEO')];
  const seo = (condition: StepCondition) => ({ ...steps[1], condition });

  it('is null for a step without a condition', () => {
    expect(describeCondition(steps[1], steps)).toBeNull();
  });

  it('says what it looks at and how, with the text', () => {
    expect(describeCondition(seo(when('previous_output', 'contains', ' blog ')), steps)).toBe(
      'the previous result contains “blog”',
    );
    expect(describeCondition(seo(when('step:1', 'not_contains', 'draft')), steps)).toBe(
      'the result of “Research” (step 1) does not contain “draft”',
    );
    expect(describeCondition(seo(when('input:topic', 'equals', 'bees')), steps, [TOPIC])).toBe(
      'the input “Topic” is exactly “bees”',
    );
    expect(describeCondition(seo(when('input:topic', 'not_equals', 'bees')), steps)).toBe(
      'the input “topic” is not exactly “bees”',
    );
  });

  it('leaves out the text for the comparisons that take none', () => {
    expect(describeCondition(seo(when('previous_output', 'is_empty', 'x')), steps)).toBe(
      'the previous result is empty',
    );
    expect(describeCondition(seo(when('step:1', 'not_empty')), steps)).toBe(
      'the result of “Research” (step 1) is not empty',
    );
  });

  it('calls the previous result of a first-stage step the text the run starts with', () => {
    const first = { ...steps[0], condition: when('previous_output', 'contains', 'x') };
    expect(describeCondition(first, steps)).toBe('the text the run starts with contains “x”');
  });

  it('is honest about a step that was removed, or one that is not there', () => {
    expect(describeCondition(seo(when('step:0', 'is_empty')), steps)).toBe(
      'a step that was removed is empty',
    );
    expect(describeCondition(seo(when('step:7', 'is_empty')), steps)).toBe(
      'something that is not there is empty',
    );
  });

  it('keeps an operator it does not know in its own words', () => {
    const odd = seo({ source: 'previous_output', operator: 'sounds_like' as never, value: 'x' });
    expect(describeCondition(odd, steps)).toBe('the previous result sounds_like “x”');
  });
});

describe('reviews', () => {
  it('are worded with how many times the work goes back', () => {
    expect(describeReview(review(2, 1))).toBe('Sends the work back to stage 2, up to 1 time');
    expect(describeReview(review(3, 4))).toBe('Sends the work back to stage 3, up to 4 times');
    expect(timesWords(1)).toBe('1 time');
    expect(timesWords(5)).toBe('5 times');
  });

  it('start as a loop to the stage right before, twice at most', () => {
    const steps = [step(1, 1), step(2, 2), step(3, 4)];
    expect(newReview(steps[2], steps)).toEqual({
      send_back_to_stage: 2,
      max_rounds: DEFAULT_REVIEW_ROUNDS,
    });
    expect(DEFAULT_REVIEW_ROUNDS).toBe(2);
  });

  it('start at stage 1 when there is no earlier stage, to be refused later', () => {
    expect(newReview(step(1, 1), [step(1, 1)]).send_back_to_stage).toBe(1);
  });

  it('start a condition that looks at the previous result and compares with nothing', () => {
    expect(newCondition()).toEqual({ source: 'previous_output', operator: 'contains', value: '' });
  });
});

describe('the operators', () => {
  it('are the six the backend knows, each in plain words', () => {
    expect(CONDITION_OPERATORS.map((option) => option.label)).toEqual([
      'contains',
      'does not contain',
      'is exactly',
      'is not exactly',
      'is empty',
      'is not empty',
    ]);
    expect(CONDITION_OPERATORS.filter((o) => !o.takesValue).map((o) => o.value)).toEqual([
      'is_empty',
      'not_empty',
    ]);
  });

  it('can be looked up by value, and an unknown one is not found', () => {
    expect(operatorOption('equals')?.label).toBe('is exactly');
    expect(operatorOption('sounds_like')).toBeUndefined();
  });
});

describe('review loops', () => {
  it('is the stages from the one the work goes back to, to the reviewer’s own', () => {
    const steps = [step(1, 1), step(2, 2), step(3, 3, 'QA', { review: review(2, 3) })];
    expect(loopOf(steps[2], steps)).toEqual({ reviewer: 3, first: 2, last: 3, maxRounds: 3 });
    expect(reviewLoops(steps)).toEqual([{ reviewer: 3, first: 2, last: 3, maxRounds: 3 }]);
  });

  it('is none for a step without a review', () => {
    expect(loopOf(step(1, 1), [step(1, 1)])).toBeNull();
    expect(reviewLoops([step(1, 1), step(2, 2)])).toEqual([]);
  });

  it.each([
    ['a stage that is not earlier', review(3, 1)],
    ['a stage no step is in', review(7, 1)],
    ['no rounds', review(1, 0)],
    ['too many rounds', review(1, 6)],
  ])('cannot work with %s', (_name, bad) => {
    const steps = [step(1, 1), step(2, 3, 'QA', { review: bad })];
    expect(loopOf(steps[1], steps)).toBeNull();
    expect(reviewLoops(steps)).toEqual([]);
  });

  it('keeps only the loop that starts first of those that share a stage, as the engine does', () => {
    const steps = [
      step(1, 1),
      step(2, 2),
      step(3, 3, 'Inner', { review: review(2, 1) }),
      step(4, 4, 'Outer', { review: review(1, 1) }),
    ];
    expect(reviewLoops(steps).map((loop) => loop.reviewer)).toEqual([4]);
  });

  it('keeps loops that do not share a stage', () => {
    const steps = [
      step(1, 1),
      step(2, 2, 'First', { review: review(1, 1) }),
      step(3, 3),
      step(4, 4, 'Second', { review: review(3, 2) }),
    ];
    expect(reviewLoops(steps).map((loop) => loop.reviewer)).toEqual([2, 4]);
  });
});

describe('roundTotals', () => {
  it('gives every step of a loop’s stages the most times it may run', () => {
    const steps = [
      step(1, 1),
      step(2, 2),
      step(3, 2),
      step(4, 3, 'QA', { review: review(2, 2) }),
      step(5, 4),
    ];
    expect([...roundTotals(steps)]).toEqual([
      [2, 3],
      [3, 3],
      [4, 3],
    ]);
  });

  it('is empty without a loop', () => {
    expect(roundTotals([step(1, 1), step(2, 2)]).size).toBe(0);
  });

  it('counts each loop on its own', () => {
    const steps = [
      step(1, 1),
      step(2, 2, 'A', { review: review(1, 1) }),
      step(3, 3),
      step(4, 4, 'B', { review: review(3, 4) }),
    ];
    expect(roundTotals(steps).get(1)).toBe(2);
    expect(roundTotals(steps).get(2)).toBe(2);
    expect(roundTotals(steps).get(3)).toBe(5);
    expect(roundTotals(steps).get(4)).toBe(5);
  });
});
