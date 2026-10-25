import { describe, expect, it } from 'vitest';

import { groupByStage, insertStep, nextStage, outputOrders, stepLabel } from './stages';
import type { PipelineStep } from '../../core/api/types';

const workflow: PipelineStep[] = [1, 2, 3].map((order) => ({
  order,
  stage: order,
  title: '',
  is_output: false,
  expected_output: '',
  prompt: 'Use {input}',
  model: 'vendor/model',
  role: '',
  allowed_tools: null,
  condition: null,
  review: null,
}));

describe('insertStep', () => {
  it('adds parallel work to the selected stage', () => {
    const steps = insertStep(workflow, { model: 'vendor/model', stage: 2, parallel: true });
    expect(steps.map((step) => step.stage)).toEqual([1, 2, 2, 3]);
    expect(steps.map((step) => step.order)).toEqual([1, 2, 3, 4]);
    expect(steps[2]).toMatchObject({ role: '', allowed_tools: null });
  });

  it('inserts a new stage and moves later work after it', () => {
    const steps = insertStep(workflow, { model: 'vendor/model', stage: 1, parallel: false });
    expect(steps.map((step) => step.stage)).toEqual([1, 2, 3, 4]);
    expect(groupByStage(steps, (step) => step.stage).map((group) => group.stage)).toEqual([
      1, 2, 3, 4,
    ]);
    expect(workflow[1].stage).toBe(2);
  });

  it('gives a new step no condition and no review', () => {
    const [, , added] = insertStep(workflow, { model: 'vendor/model', stage: 2, parallel: true });
    expect([added.condition, added.review]).toEqual([null, null]);
  });

  it('keeps a condition on the step it looks at when the steps are numbered again', () => {
    // Step 3 looks at step 2. A new stage after stage 1 puts the new step second.
    const steps = workflow.map((step) =>
      step.order === 3
        ? { ...step, condition: { source: 'step:2', operator: 'not_empty' as const, value: '' } }
        : step,
    );

    const inserted = insertStep(steps, { model: 'vendor/model', stage: 1, parallel: false });

    const looking = inserted.find((step) => step.condition !== null);
    const looked = inserted.find((step) => `step:${step.order}` === looking?.condition?.source);
    expect(looking?.order).toBe(4);
    // It still looks at the step that was step 2: now step 3, in stage 3.
    expect(looked).toMatchObject({ order: 3, stage: 3 });
  });

  it('keeps a review going back to the stage it meant when a stage opens before it', () => {
    const steps = workflow.map((step) =>
      step.order === 3 ? { ...step, review: { send_back_to_stage: 2, max_rounds: 2 } } : step,
    );

    const inserted = insertStep(steps, { model: 'vendor/model', stage: 1, parallel: false });

    // Stage 2 is stage 3 now, and the reviewer (stage 3) is stage 4.
    const reviewer = inserted.find((step) => step.review !== null);
    expect(reviewer?.stage).toBe(4);
    expect(reviewer?.review?.send_back_to_stage).toBe(3);
  });

  it('leaves a review alone when the new stage opens after the stage it goes back to', () => {
    const steps = workflow.map((step) =>
      step.order === 3 ? { ...step, review: { send_back_to_stage: 1, max_rounds: 2 } } : step,
    );

    const inserted = insertStep(steps, { model: 'vendor/model', stage: 2, parallel: false });

    expect(inserted.find((step) => step.review !== null)?.review?.send_back_to_stage).toBe(1);
  });

  it('adds parallel work without moving any stage a review points at', () => {
    const steps = workflow.map((step) =>
      step.order === 3 ? { ...step, review: { send_back_to_stage: 2, max_rounds: 2 } } : step,
    );

    const inserted = insertStep(steps, { model: 'vendor/model', stage: 1, parallel: true });

    expect(inserted.find((step) => step.review !== null)?.review?.send_back_to_stage).toBe(2);
  });
});

describe('groupByStage', () => {
  it('orders stages ascending and keeps item order inside a stage', () => {
    const steps = [
      { id: 'c', stage: 2 },
      { id: 'a', stage: 1 },
      { id: 'b', stage: 1 },
    ];
    const groups = groupByStage(steps, (step) => step.stage);
    expect(groups.map((group) => group.stage)).toEqual([1, 2]);
    expect(groups[0].items.map((step) => step.id)).toEqual(['a', 'b']);
  });
});

describe('nextStage', () => {
  it('places a new step after the last stage', () => {
    expect(nextStage([{ stage: 1 }, { stage: 1 }, { stage: 3 }])).toBe(4);
    expect(nextStage([])).toBe(1);
  });
});

describe('outputOrders', () => {
  it('uses the marked steps wherever they are', () => {
    const steps = [
      { order: 1, stage: 1, is_output: true },
      { order: 2, stage: 2, is_output: false },
    ];
    expect([...outputOrders(steps)]).toEqual([1]);
  });

  it('falls back to the last stage when nothing is marked', () => {
    const steps = [
      { order: 1, stage: 1, is_output: false },
      { order: 2, stage: 2, is_output: false },
      { order: 3, stage: 2, is_output: false },
    ];
    expect([...outputOrders(steps)]).toEqual([2, 3]);
  });
});

describe('stepLabel', () => {
  it('prefers the title and falls back to the position', () => {
    expect(stepLabel({ order: 2, title: ' Tweet ' })).toBe('Tweet');
    expect(stepLabel({ order: 2, title: '' })).toBe('Step 2');
  });
});
