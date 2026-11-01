import { describe, expect, it } from 'vitest';

import type { Run } from '../../../core/api/types';
import { makeApproval, makeRun, runStep } from '../testData';
import { definitionOf, deliverableState, titleOf, type DeliverableView } from './reportModel';
import { ENDED, flowRun, stepOf, teamRun } from './reportTestData';
import { rowStatus, slotWords } from './stepCopy';

/** Any step of the run as a deliverable, in the state the model gives it. */
function viewOf(run: Run, order: number): DeliverableView {
  const step = stepOf(run, order);
  return {
    step,
    definition: definitionOf(run, step),
    title: titleOf(step),
    role: '',
    state: deliverableState(step, run),
  };
}

const slot = (run: Run, order: number) => slotWords(viewOf(run, order), run);

describe('slotWords', () => {
  it('not started yet, while the run is queued', () => {
    const run = makeRun({
      status: 'queued',
      steps: [runStep(1, 'pending'), runStep(2, 'pending')],
    });
    expect(slot(run, 2)).toBe('Not started yet');
  });

  it('starts when the stage before is done', () => {
    const run = makeRun({ steps: [runStep(1, 'running'), runStep(2, 'pending')] });
    expect(slot(run, 2)).toBe('Starts when Research is done');
  });

  it('starts when both parallel steps before are done', () => {
    const run = teamRun([['succeeded'], ['running'], ['running'], ['pending']]);
    expect(slot(run, 4)).toBe('Starts when Blog post and LinkedIn post are done');
  });

  it('starting, once nothing before it is left', () => {
    expect(slot(makeRun(), 3)).toBe('Starting…');
  });

  it('being written', () => {
    expect(slot(makeRun(), 2)).toBe('Being written');
  });

  it('being revised, in which round out of how many', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(slot(run, 2)).toBe('Being revised · round 2 of 3');
  });

  it('being revised as soon as the reviewer sends it back', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(slot(run, 3)).toBe('Being revised · round 2 of 3');
  });

  it('waiting for your OK', () => {
    const run = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });
    expect(slot(run, 2)).toBe('Waiting for your OK');
  });

  it('not finished: why its step stopped', () => {
    const run = makeRun({
      status: 'failed',
      ...ENDED,
      error: { code: 'provider_timeout', detail: 'The agent timed out.' },
      steps: [
        runStep(1, 'succeeded'),
        runStep(2, 'failed'),
        { ...runStep(3, 'failed'), error: null },
      ],
    });
    expect(slot(run, 2)).toBe(
      'Not finished: it stopped because the AI service did not answer in time.',
    );
    expect(slot(run, 3)).toBe('Not finished: the run stopped before it was done.');
  });

  it('not finished: you stopped the run', () => {
    const run = makeRun({
      status: 'cancelled',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'cancelled'), runStep(3, 'pending')],
    });
    expect(slot(run, 2)).toBe('Not finished: you stopped the run before it was done.');
    expect(slot(run, 3)).toBe('Not finished: the run stopped before it started.');
  });

  it('not finished: the server restarted', () => {
    const run = makeRun({
      status: 'interrupted',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'cancelled'), runStep(3, 'pending')],
    });
    expect(slot(run, 2)).toBe('Not finished: the server restarted before it was done.');
  });

  it('not made: names the condition that was not met', () => {
    const run = flowRun(
      [['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }], ['skipped']],
      { status: 'succeeded', ...ENDED },
    );
    expect(slot(run, 4)).toBe(
      'Not made: its condition was not met. It runs only if the previous result contains “blog”.',
    );
  });

  it('not made, for a step whose condition the definition no longer holds', () => {
    const run = makeRun({
      status: 'succeeded',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded'), runStep(3, 'skipped')],
    });
    expect(slot(run, 3)).toBe('Not made: its condition was not met.');
  });

  it('says nothing once the deliverable is ready', () => {
    const run = makeRun({ steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded')] });
    expect(slot(run, 2)).toBe('');
  });
});

describe('rowStatus', () => {
  const started = Date.parse('2026-10-24T10:00:00Z');
  const row = (run: Run, order: number) => rowStatus(stepOf(run, order), run, started + 5000);

  it('done, with how long it took', () => {
    expect(row(makeRun(), 1)).toEqual({ icon: 'done', words: 'Done · 4.0 s' });
  });

  it('working, with how long so far', () => {
    expect(row(makeRun(), 2)).toEqual({ icon: 'running', words: 'Working · 5.0 s' });
  });

  it('working on a later round', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(row(run, 2)).toEqual({ icon: 'running', words: 'Working on round 2 of 3 · 5.0 s' });
  });

  it('starts when the stage before is done, or is starting', () => {
    const run = teamRun([['succeeded'], ['running'], ['succeeded'], ['pending']]);
    expect(row(run, 4)).toEqual({ icon: 'waiting', words: 'Starts when Blog post is done' });
    expect(row(makeRun(), 3)).toEqual({ icon: 'waiting', words: 'Starting…' });
  });

  it('not started yet, in a queued run', () => {
    const run = makeRun({
      status: 'queued',
      steps: [runStep(1, 'pending'), runStep(2, 'pending')],
    });
    expect(row(run, 2)).toEqual({ icon: 'waiting', words: 'Not started yet' });
  });

  it('waiting for your OK', () => {
    const run = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });
    expect(row(run, 2)).toEqual({ icon: 'needsOk', words: 'Waiting for your OK' });
  });

  it('stopped because of what went wrong, or before it finished', () => {
    const run = makeRun({
      status: 'failed',
      ...ENDED,
      steps: [
        runStep(1, 'succeeded'),
        runStep(2, 'failed'),
        { ...runStep(3, 'failed'), error: null },
      ],
    });
    expect(row(run, 2)).toEqual({
      icon: 'failed',
      words: 'Stopped because the AI service did not answer in time.',
    });
    expect(row(run, 3)).toEqual({ icon: 'failed', words: 'Stopped before it finished.' });
  });

  it('stopped before it finished, and did not run', () => {
    const run = makeRun({
      status: 'cancelled',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'cancelled'), runStep(3, 'pending')],
    });
    expect(row(run, 2)).toEqual({ icon: 'stopped', words: 'Stopped before it finished.' });
    expect(row(run, 3)).toEqual({ icon: 'pending', words: 'Did not run.' });
  });

  it('skipped, with the condition', () => {
    const run = flowRun(
      [['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }], ['skipped']],
      { status: 'succeeded', ...ENDED },
    );
    expect(row(run, 4)).toEqual({
      icon: 'skipped',
      words:
        'Skipped: its condition was not met. It runs only if the previous result contains “blog”.',
    });
  });
});
