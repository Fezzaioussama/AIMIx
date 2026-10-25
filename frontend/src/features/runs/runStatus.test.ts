import { describe, expect, it } from 'vitest';

import type { Pipeline } from '../../core/api/types';
import { finishedStepCount, isActive, isResumable, ranThisVersion } from './runStatus';
import { makeRun } from './testData';

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
});
