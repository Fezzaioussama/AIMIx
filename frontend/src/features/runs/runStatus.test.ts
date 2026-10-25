import { describe, expect, it } from 'vitest';

import type { Pipeline } from '../../core/api/types';
import { finishedStepCount, isActive, isResumable, ranThisVersion } from './runStatus';
import { makeRun, runStep } from './testData';

describe('run statuses', () => {
  it('tells active runs from resumable ones', () => {
    expect(['queued', 'running'].every((status) => isActive(status as 'queued'))).toBe(true);
    expect(isActive('interrupted')).toBe(false);
    expect(isResumable('failed') && isResumable('cancelled') && isResumable('interrupted')).toBe(
      true,
    );
    expect(isResumable('succeeded') || isResumable('running')).toBe(false);
  });

  it('treats a run waiting for an approval as active: stoppable, polled, not resumable', () => {
    expect(isActive('waiting')).toBe(true);
    expect(isResumable('waiting')).toBe(false);
  });

  it('counts the steps that are done', () => {
    expect(finishedStepCount(makeRun())).toBe(1);
  });

  it('counts a skipped step as done: it will not run, and nothing is waiting on it', () => {
    const run = makeRun({
      steps: [runStep(1, 'succeeded'), runStep(2, 'skipped'), runStep(3, 'failed')],
    });
    expect(finishedStepCount(run)).toBe(2);
  });
});

describe('ranThisVersion', () => {
  const run = makeRun();
  const pipeline: Pipeline = {
    id: 3,
    name: 'Launch kit',
    inputs: [],
    steps: run.definition.steps.map((step, index) => ({ ...step, id: index + 10 })),
  };

  it('accepts the version the run executed, whatever the step ids', () => {
    expect(ranThisVersion(run, pipeline)).toBe(true);
  });

  it('refuses an edited version or another pipeline', () => {
    const edited = {
      ...pipeline,
      steps: pipeline.steps.map((step, index) =>
        index === 1 ? { ...step, prompt: 'Something else {input}' } : step,
      ),
    };
    expect(ranThisVersion(run, edited)).toBe(false);
    expect(ranThisVersion(run, { ...pipeline, id: 4 })).toBe(false);
    expect(
      ranThisVersion(run, { ...pipeline, inputs: [{ name: 'topic', label: '', description: '' }] }),
    ).toBe(false);
  });

  it('refuses a version whose condition or review loop was changed since the run', () => {
    const withCondition = {
      ...pipeline,
      steps: pipeline.steps.map((step, index) =>
        index === 1
          ? { ...step, condition: { source: 'step:1', operator: 'is_empty' as const, value: '' } }
          : step,
      ),
    };
    const withReview = {
      ...pipeline,
      steps: pipeline.steps.map((step, index) =>
        index === 2 ? { ...step, review: { send_back_to_stage: 1, max_rounds: 2 } } : step,
      ),
    };
    expect(ranThisVersion(run, withCondition)).toBe(false);
    expect(ranThisVersion(run, withReview)).toBe(false);
  });
});
