import { describe, expect, it } from 'vitest';

import type { Run } from '../../../core/api/types';
import { makeApproval, makeRun, runStep } from '../testData';
import {
  FAILURE_WORDS,
  failureReason,
  keptSentence,
  OUTCOME_COPY,
  settingsHint,
  type OutcomeWords,
} from './outcomeCopy';
import { reportModel } from './reportModel';
import { defined, ENDED, runOf, teamRun } from './reportTestData';

/** The header's words for a run, through the outcome its model finds. */
function words(run: Run): OutcomeWords {
  const model = reportModel(run);
  return OUTCOME_COPY[model.outcome]({ run, model });
}

const failedRun = (code: string, detail = 'The agent timed out.') =>
  makeRun({
    status: 'failed',
    ...ENDED,
    error: { code, detail },
    steps: [runStep(1, 'succeeded'), runStep(2, 'failed'), runStep(3, 'failed')],
  });

describe('OUTCOME_COPY', () => {
  it('queued', () => {
    const run = makeRun({
      status: 'queued',
      started_at: null,
      steps: [runStep(1, 'pending'), runStep(2, 'pending'), runStep(3, 'pending')],
    });
    expect(words(run)).toEqual({
      heading: 'Your team is lined up',
      sentence: 'It starts as soon as a slot is free.',
    });
  });

  it('running: who works now, and how many agents are done', () => {
    expect(words(makeRun())).toEqual({
      heading: 'Your team is working',
      sentence: 'Now working: Draft. 1 of 3 agents done.',
      aside: 'Each deliverable appears below as soon as it is ready, even if you leave this page.',
    });
  });

  it('running: names agents working at the same time', () => {
    const run = makeRun({
      steps: [runStep(1, 'succeeded'), runStep(2, 'running'), runStep(3, 'running')],
    });
    expect(words(run).sentence).toBe('Now working: Draft and Summary. 1 of 3 agents done.');
  });

  it('running: between two agents', () => {
    const run = makeRun({
      steps: [runStep(1, 'succeeded'), runStep(2, 'pending'), runStep(3, 'pending')],
    });
    expect(words(run).sentence).toBe('Getting the next agent ready. 1 of 3 agents done.');
  });

  it('running: a team of one agent', () => {
    const run = runOf([defined(1, 1, 'Draft', { is_output: true })], [['running']]);
    expect(words(run).sentence).toBe('Now working: Draft. 0 of 1 agent done.');
  });

  it('checking', () => {
    const run = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    expect(words(run)).toEqual({
      heading: 'Your work is being checked',
      sentence: 'You can read your deliverables below while the check runs.',
    });
  });

  it('fixing: the round, out of the most the loop runs', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(words(run)).toEqual({
      heading: 'Fixing what the check found',
      sentence:
        'Your team is working on round 2 of 3. Each deliverable appears below again as soon as it is ready.',
    });
  });

  it('waiting for one request: who asks, and for what in plain words', () => {
    const run = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });
    expect(words(run)).toEqual({
      heading: 'Your team needs your OK',
      sentence: 'Draft wants to use “Send email” from crm. The run waits until you answer below.',
    });
  });

  it('waiting for several requests', () => {
    const run = makeRun({
      status: 'waiting',
      pending_approvals: [makeApproval(), makeApproval({ id: 32, step_order: 3 })],
    });
    expect(words(run)).toEqual({
      heading: 'Your team needs your OK',
      sentence: '2 requests are waiting for your answer below.',
    });
  });

  it('done: how many deliverables, and how long it took', () => {
    const run = makeRun({
      status: 'succeeded',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded'), runStep(3, 'succeeded')],
    });
    expect(words(run)).toEqual({
      heading: '2 deliverables ready',
      sentence: 'Done in 4 min 54 s.',
    });
  });

  it('done: names a deliverable that was skipped', () => {
    const run = makeRun({
      status: 'succeeded',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded'), runStep(3, 'skipped')],
    });
    expect(words(run)).toEqual({
      heading: '1 deliverable ready',
      sentence: 'Done in 4 min 54 s. Summary was skipped because its condition was not met.',
    });
  });

  it('done: names several skipped deliverables together', () => {
    const outputs = ['Post', 'Thread', 'Email'].map((title, index) =>
      defined(index + 1, 1, title, { is_output: true }),
    );
    const run = runOf(outputs, [['succeeded'], ['skipped'], ['skipped']], {
      status: 'succeeded',
      ...ENDED,
    });
    expect(words(run).sentence).toBe(
      'Done in 4 min 54 s. Thread and Email were skipped because their condition was not met.',
    );
  });

  it('done with no deliverable', () => {
    const run = makeRun({
      status: 'succeeded',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'skipped'), runStep(3, 'skipped')],
    });
    expect(words(run)).toEqual({
      heading: 'Done, with no deliverable',
      sentence:
        'The agents that make the deliverables were skipped because their condition was not met.',
    });
  });

  it('the spending limit: the server’s words, then what to do and what Resume keeps', () => {
    const run = failedRun(
      'budget_exceeded',
      // RunMeter.check in backend/api/services/run_budget.py
      'This run stopped at $0.52 because it reached its $0.50 limit.',
    );
    expect(words(run)).toEqual({
      heading: 'The run stopped at its spending limit',
      sentence:
        'This run stopped at $0.52 because it reached its $0.50 limit. Raise the limit below to go on. Resume keeps Research and starts again from Draft and Summary.',
    });
  });

  it('failed: which step, why, and what Resume keeps', () => {
    expect(words(failedRun('provider_timeout'))).toEqual({
      heading: 'The run stopped before it finished',
      sentence:
        'Draft stopped because the AI service did not answer in time. Resume keeps Research and starts again from Draft and Summary.',
    });
  });

  it('failed with no failed step', () => {
    const run = makeRun({
      status: 'failed',
      ...ENDED,
      error: { code: 'server_error', detail: 'An unexpected error occurred.' },
      steps: [runStep(1, 'pending'), runStep(2, 'pending'), runStep(3, 'pending')],
    });
    expect(words(run).sentence).toBe(
      'It stopped because something went wrong on our side. Nothing was finished yet, so Resume starts again from the beginning.',
    );
  });

  it('stopped', () => {
    const run = makeRun({
      status: 'cancelled',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'cancelled'), runStep(3, 'cancelled')],
    });
    expect(words(run)).toEqual({
      heading: 'You stopped the run',
      sentence: 'Resume keeps Research and starts again from Draft and Summary.',
    });
  });

  it('interrupted', () => {
    const run = makeRun({
      status: 'interrupted',
      ...ENDED,
      steps: [runStep(1, 'succeeded'), runStep(2, 'cancelled'), runStep(3, 'pending')],
    });
    expect(words(run)).toEqual({
      heading: 'The run was interrupted',
      sentence:
        'The server restarted while your team was working. Resume keeps Research and starts again from Draft and Summary.',
    });
  });
});

describe('failureReason', () => {
  it.each(Object.entries(FAILURE_WORDS))('words %s', (code, reason) => {
    expect(failureReason(code)).toBe(reason);
  });

  it.each([
    ['provider_timeout', 'the AI service did not answer in time'],
    ['provider_unavailable', 'the AI service could not be reached'],
    ['provider_not_configured', 'no AI service is set up for your account'],
    ['upstream_response_invalid', 'the AI service sent an answer that could not be used'],
    ['tool_unavailable', 'a tool it needs is not available'],
    ['server_error', 'something went wrong on our side'],
  ])('says %s as the copy deck does', (code, reason) => {
    expect(failureReason(code)).toBe(reason);
  });

  it('falls back to “something went wrong”', () => {
    expect(failureReason('teapot')).toBe('something went wrong');
    expect(failureReason('toString')).toBe('something went wrong');
    expect(failureReason(undefined)).toBe('something went wrong');
    expect(failureReason(null)).toBe('something went wrong');
  });
});

describe('keptSentence', () => {
  const stopped = (states: Parameters<typeof teamRun>[0]) =>
    teamRun(states, { status: 'cancelled', ...ENDED });

  it('nothing finished', () => {
    expect(keptSentence(stopped([['cancelled'], ['pending'], ['pending'], ['pending']]))).toBe(
      'Nothing was finished yet, so Resume starts again from the beginning.',
    );
  });

  it('one finished', () => {
    expect(keptSentence(stopped([['succeeded'], ['cancelled'], ['cancelled'], ['pending']]))).toBe(
      'Resume keeps Research and starts again from Blog post and LinkedIn post.',
    );
  });

  it('two finished', () => {
    expect(keptSentence(stopped([['succeeded'], ['succeeded'], ['cancelled'], ['pending']]))).toBe(
      'Resume keeps Research and Blog post and starts again from LinkedIn post.',
    );
  });

  it('more than two finished are counted', () => {
    expect(keptSentence(stopped([['succeeded'], ['succeeded'], ['succeeded'], ['failed']]))).toBe(
      'Resume keeps the work of 3 agents and starts again from Final check.',
    );
  });

  it('all finished: Resume only finishes the run', () => {
    expect(
      keptSentence(
        stopped([['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }]]),
      ),
    ).toBe('Resume keeps the work of 4 agents and finishes the run.');
  });
});

describe('settingsHint', () => {
  it('tells how to set up an AI service when none is', () => {
    expect(settingsHint(failedRun('provider_not_configured'))).toBe(
      'Add an AI service key in Settings, then resume.',
    );
  });

  it('has nothing to add for other failures', () => {
    expect(settingsHint(failedRun('provider_timeout'))).toBeNull();
    expect(settingsHint(makeRun())).toBeNull();
  });
});
