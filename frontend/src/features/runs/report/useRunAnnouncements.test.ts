import { renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { Run } from '../../../core/api/types';
import { makeApproval, makeRun, runStep } from '../testData';
import type { OutcomeFacts } from './outcomeCopy';
import { reportModel } from './reportModel';
import { ENDED, teamRun } from './reportTestData';
import { announcementFor, useRunAnnouncements } from './useRunAnnouncements';

function facts(run: Run): OutcomeFacts {
  return { run, model: reportModel(run) };
}

function said(previous: Run, next: Run): string {
  return announcementFor(facts(previous), facts(next));
}

/** Research done, Draft writing, Summary next: makeRun's run in flight. */
const going = makeRun();
const draftDone = makeRun({
  steps: [
    runStep(1, 'succeeded', 'Research notes'),
    runStep(2, 'succeeded', 'Draft text'),
    runStep(3, 'running'),
  ],
});
const allDone = makeRun({
  status: 'succeeded',
  finished_at: '2026-10-24T10:00:09Z',
  steps: [
    runStep(1, 'succeeded', 'Research notes'),
    runStep(2, 'succeeded', 'Draft text'),
    runStep(3, 'succeeded', 'Summary text'),
  ],
});
const stoppedShort = (overrides: Partial<Run>) =>
  makeRun({
    finished_at: '2026-10-24T10:00:05Z',
    steps: [
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'failed'),
      runStep(3, 'cancelled'),
    ],
    ...overrides,
  });

describe('announcementFor', () => {
  it('says nothing when nothing worth hearing changed', () => {
    expect(said(going, makeRun())).toBe('');
  });

  it('names the deliverables that have just become ready', () => {
    expect(said(going, draftDone)).toBe('Draft ready.');
    const both = makeRun({
      steps: [...allDone.steps.slice(0, 2), runStep(3, 'succeeded', 'Summary text')],
    });
    expect(said(going, both)).toBe('Draft and Summary ready.');
  });

  it('tells that the team finished, and that the reviewer approved the work', () => {
    const checking = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    const approved = teamRun(
      [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }]],
      { status: 'succeeded', ...ENDED },
    );

    expect(said(checking, approved)).toBe(
      'Your team finished: 2 deliverables ready, approved by the Orchestrator.',
    );
    expect(said(draftDone, allDone)).toBe('Your team finished: 2 deliverables ready.');
  });

  it('never says the work was approved when the reviewer still asked for fixes', () => {
    const lastRound = teamRun([
      ['succeeded'],
      ['succeeded', { rounds: 3 }],
      ['succeeded', { rounds: 3 }],
      ['running', { rounds: 3 }],
    ]);
    const kept = teamRun(
      [
        ['succeeded'],
        ['succeeded', { rounds: 3 }],
        ['succeeded', { rounds: 3 }],
        ['succeeded', { rounds: 3, verdict: 'revise' }],
      ],
      { status: 'succeeded', ...ENDED },
    );

    expect(said(lastRound, kept)).toBe('Your team finished: 2 deliverables ready.');
  });

  it('says when the team finished with no deliverable', () => {
    const skipped = makeRun({
      status: 'succeeded',
      ...ENDED,
      steps: [
        runStep(1, 'succeeded', 'Research notes'),
        runStep(2, 'skipped'),
        runStep(3, 'skipped'),
      ],
    });

    expect(said(going, skipped)).toBe('Your team finished, with no deliverable.');
  });

  it('says once that the reviewer asked for fixes, and which round has started', () => {
    const checking = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    const sentBack = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    const rewriting = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);

    expect(said(checking, sentBack)).toBe(
      'The Orchestrator asked for fixes. Round 2 of 3 has started.',
    );
    expect(said(sentBack, rewriting)).toBe('');
  });

  it('says what the team needs your OK for', () => {
    const waiting = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });
    const twice = makeRun({
      status: 'waiting',
      pending_approvals: [makeApproval(), makeApproval({ id: 32, step_order: 1 })],
    });

    expect(said(going, waiting)).toBe(
      'Your team needs your OK: Draft wants to use “Send email” from crm.',
    );
    expect(said(going, twice)).toBe(
      'Your team needs your OK: 2 requests are waiting for your answer.',
    );
  });

  it.each([
    [
      'failed',
      stoppedShort({ status: 'failed', error: { code: 'provider_timeout', detail: 'x' } }),
      'The run stopped before it finished.',
    ],
    [
      'at its limit',
      stoppedShort({ status: 'failed', error: { code: 'budget_exceeded', detail: 'x' } }),
      'The run stopped at its spending limit.',
    ],
    ['stopped', stoppedShort({ status: 'cancelled' }), 'You stopped the run.'],
    ['interrupted', stoppedShort({ status: 'interrupted' }), 'The run was interrupted.'],
  ])('says why the run ended: %s', (_name, ended, line) => {
    expect(said(going, ended)).toBe(line);
  });

  it('says the team is working again once a stopped run resumes', () => {
    const stopped = stoppedShort({ status: 'cancelled' });

    expect(said(stopped, makeRun({ status: 'running' }))).toBe('Your team is working again.');
    // Queued to running is not news.
    expect(said(makeRun({ status: 'queued' }), going)).toBe('');
  });

  it('confirms an answer to a request: the team is working again', () => {
    const waiting = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });

    expect(said(waiting, going)).toBe('Your team is working again.');
  });

  it('puts a change of status before the deliverables that came with it', () => {
    expect(said(going, allDone)).toBe('Your team finished: 2 deliverables ready.');
  });
});

describe('useRunAnnouncements', () => {
  it('says nothing as the run first shows, then each change, again when it repeats', () => {
    const { result, rerender } = renderHook(
      ({ run }) => useRunAnnouncements(run, reportModel(run)),
      { initialProps: { run: going } },
    );
    expect(result.current).toBe('');

    rerender({ run: draftDone });
    expect(result.current).toBe('Draft ready.');

    // A poll with nothing new keeps the last line, so nothing is said again.
    rerender({ run: { ...draftDone } });
    expect(result.current).toBe('Draft ready.');

    // The same line once more differs by a trailing space, so it is heard.
    rerender({ run: going });
    rerender({ run: { ...draftDone } });
    expect(result.current).toBe('Draft ready. ');
    rerender({ run: going });
    rerender({ run: { ...draftDone } });
    expect(result.current).toBe('Draft ready.');
  });
});
