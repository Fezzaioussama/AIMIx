import { describe, expect, it } from 'vitest';

import type { Run, RunStatus, RunStep, RunStepStatus } from '../../../core/api/types';
import { makeApproval, makeRun, runStep } from '../testData';
import {
  definitionOf,
  deliverablesOf,
  deliverableState,
  keptParts,
  outcomeOf,
  reportIds,
  reportModel,
  reviewerOf,
  runningTitles,
  waitsFor,
  type DeliverableState,
  type OutcomeKind,
} from './reportModel';
import { defined, ENDED, flowRun, runOf, stepOf, TEAM, teamRun } from './reportTestData';

const ORDERS = (steps: RunStep[]) => steps.map((step) => step.step_order);

describe('deliverableState', () => {
  // Draft (order 2) in each state, its run in each status.
  it.each<[RunStepStatus, RunStatus, Partial<RunStep>, DeliverableState]>([
    ['pending', 'queued', {}, 'queued'],
    ['pending', 'running', {}, 'waiting'],
    ['pending', 'waiting', {}, 'waiting'],
    ['pending', 'failed', {}, 'notFinished'],
    ['pending', 'cancelled', {}, 'notFinished'],
    ['pending', 'interrupted', {}, 'notFinished'],
    ['running', 'running', {}, 'writing'],
    ['running', 'running', { rounds: 2 }, 'revising'],
    ['succeeded', 'running', {}, 'ready'],
    ['succeeded', 'succeeded', {}, 'ready'],
    ['skipped', 'succeeded', {}, 'skipped'],
    ['failed', 'failed', {}, 'notFinished'],
    ['cancelled', 'cancelled', {}, 'notFinished'],
    ['cancelled', 'interrupted', {}, 'notFinished'],
  ])('a %s step in a %s run (%o) is %s', (stepStatus, runStatus, fields, state) => {
    const draft = { ...runStep(2, stepStatus), ...fields };
    const run = makeRun({ status: runStatus, steps: [runStep(1, 'succeeded', 'notes'), draft] });
    expect(deliverableState(draft, run)).toBe(state);
  });

  it('waits for your OK while the step asks to use a tool', () => {
    const run = makeRun({ status: 'waiting', pending_approvals: [makeApproval()] });
    expect(deliverableState(stepOf(run, 2), run)).toBe('needsOk');
    expect(deliverableState(stepOf(run, 3), run)).toBe('waiting');
  });

  it('is being revised once the reviewer sent it back, before its step starts again', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(deliverableState(stepOf(run, 2), run)).toBe('revising');
    expect(deliverableState(stepOf(run, 3), run)).toBe('revising');
  });

  it('is ready again for a parallel writer that already finished the new round', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(deliverableState(stepOf(run, 2), run)).toBe('revising');
    expect(deliverableState(stepOf(run, 3), run)).toBe('ready');
  });

  it('keeps an earlier round readable once the run stopped during the fixes', () => {
    const run = teamRun(
      [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'revise' }]],
      { status: 'cancelled', ...ENDED },
    );
    expect(deliverableState(stepOf(run, 2), run)).toBe('ready');
  });

  it('waits again for a skipped step the reviewer sent back, as it may run this time', () => {
    const definition = [
      defined(1, 1, 'Draft', { is_output: true }),
      defined(2, 1, 'Extra', { is_output: true }),
      defined(3, 2, 'Check', { review: { send_back_to_stage: 1, max_rounds: 1 } }),
    ];
    const run = runOf(definition, [
      ['succeeded'],
      ['skipped'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(deliverableState(stepOf(run, 2), run)).toBe('waiting');
  });
});

describe('deliverablesOf and reviewerOf', () => {
  it('lists the outputs in run order, without the reviewer', () => {
    const run = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    expect(ORDERS(deliverablesOf(run))).toEqual([2, 3]);
    expect(reviewerOf(run)?.step.step_order).toBe(4);
    expect(reviewerOf(run)?.definition.role).toBe('Orchestrator');
  });

  it('orders by stage, then by order within a stage', () => {
    const definition = [
      defined(1, 2, 'Late', { is_output: true }),
      defined(2, 1, 'Early', { is_output: true }),
      defined(3, 1, 'Early too', { is_output: true }),
    ];
    const run = runOf(definition, [['pending'], ['pending'], ['pending']]);
    expect(ORDERS(deliverablesOf(run))).toEqual([2, 3, 1]);
  });

  it('makes the reviewer the deliverable when it is the only output, with no reviewer then', () => {
    const definition = TEAM.map((step) => ({ ...step, is_output: step.order === 4 }));
    const run = runOf(definition, [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded']]);
    expect(ORDERS(deliverablesOf(run))).toEqual([4]);
    expect(reviewerOf(run)).toBeNull();
  });

  it('has no reviewer when no step reviews', () => {
    expect(reviewerOf(makeRun())).toBeNull();
  });
});

describe('outcomeOf', () => {
  const revised: Parameters<typeof teamRun>[0] = [
    ['succeeded'],
    ['running', { rounds: 2 }],
    ['succeeded', { rounds: 2 }],
    ['succeeded', { verdict: 'revise' }],
  ];

  it.each<[string, Run, OutcomeKind]>([
    ['queued', makeRun({ status: 'queued' }), 'queued'],
    ['running', makeRun(), 'running'],
    [
      'checking: the reviewer runs',
      teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]),
      'checking',
    ],
    [
      'checking the revised work',
      teamRun([
        ['succeeded'],
        ['succeeded', { rounds: 2 }],
        ['succeeded', { rounds: 2 }],
        ['running', { rounds: 2 }],
      ]),
      'checking',
    ],
    ['fixing: a writer runs round 2', teamRun(revised), 'fixing'],
    [
      'fixing: REVISE given, nothing started again yet',
      teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'revise' }]]),
      'fixing',
    ],
    [
      'running: REVISE at the limit keeps the work',
      teamRun([
        ['succeeded'],
        ['succeeded', { rounds: 3 }],
        ['succeeded', { rounds: 3 }],
        ['succeeded', { rounds: 3, verdict: 'revise' }],
      ]),
      'running',
    ],
    ['waiting', makeRun({ status: 'waiting', pending_approvals: [makeApproval()] }), 'waiting'],
    [
      'done',
      makeRun({
        status: 'succeeded',
        ...ENDED,
        steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded'), runStep(3, 'skipped')],
      }),
      'done',
    ],
    [
      'done with nothing made: every output skipped',
      makeRun({
        status: 'succeeded',
        ...ENDED,
        steps: [runStep(1, 'succeeded'), runStep(2, 'skipped'), runStep(3, 'skipped')],
      }),
      'doneNothing',
    ],
    [
      'the spending limit',
      makeRun({
        status: 'failed',
        error: { code: 'budget_exceeded', detail: 'Limit reached.' },
        steps: [runStep(1, 'succeeded'), runStep(2, 'failed'), runStep(3, 'failed')],
      }),
      'limit',
    ],
    [
      'failed',
      makeRun({
        status: 'failed',
        error: { code: 'provider_timeout', detail: 'The agent timed out.' },
        steps: [runStep(1, 'succeeded'), runStep(2, 'failed'), runStep(3, 'failed')],
      }),
      'failed',
    ],
    [
      'failed with no failed step',
      makeRun({
        status: 'failed',
        error: { code: 'server_error', detail: 'An unexpected error occurred.' },
        steps: [runStep(1, 'pending'), runStep(2, 'pending'), runStep(3, 'pending')],
      }),
      'failed',
    ],
    ['stopped', makeRun({ status: 'cancelled', ...ENDED }), 'stopped'],
    ['interrupted', makeRun({ status: 'interrupted', ...ENDED }), 'interrupted'],
    ['no steps yet', makeRun({ status: 'queued', started_at: null, steps: [] }), 'queued'],
  ])('%s', (_name, run, outcome) => {
    expect(outcomeOf(run, reviewerOf(run))).toBe(outcome);
  });

  it('waits for your OK during the fixes', () => {
    const run = teamRun(revised, {
      status: 'waiting',
      pending_approvals: [makeApproval({ step_order: 2 })],
    });
    expect(outcomeOf(run, reviewerOf(run))).toBe('waiting');
  });
});

describe('waitsFor', () => {
  it('names the unfinished steps of the stage before', () => {
    const run = teamRun([['succeeded'], ['running'], ['succeeded'], ['pending']]);
    expect(waitsFor(stepOf(run, 4), run)).toEqual(['Blog post']);
  });

  it('names both parallel steps while both work', () => {
    const run = teamRun([['succeeded'], ['running'], ['running'], ['pending']]);
    expect(waitsFor(stepOf(run, 4), run)).toEqual(['Blog post', 'LinkedIn post']);
  });

  it('is empty once the stages before are final', () => {
    const run = makeRun({
      steps: [runStep(1, 'succeeded'), runStep(2, 'running'), runStep(3, 'pending')],
    });
    expect(waitsFor(stepOf(run, 3), run)).toEqual([]);
  });

  it('counts a step sent back by its reviewer as not final', () => {
    const run = flowRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
      ['pending'],
    ]);
    expect(waitsFor(stepOf(run, 4), run)).toEqual(['QA']);
  });
});

describe('keptParts and runningTitles', () => {
  it('keeps the finished steps and starts again from the first unfinished stage', () => {
    const run = makeRun({
      status: 'failed',
      steps: [runStep(1, 'succeeded'), runStep(2, 'failed'), runStep(3, 'failed')],
    });
    expect(keptParts(run)).toEqual({ kept: ['Research'], from: ['Draft', 'Summary'] });
  });

  it('starts again from only the unfinished one of a stage', () => {
    const run = makeRun({
      status: 'cancelled',
      steps: [runStep(1, 'succeeded'), runStep(2, 'succeeded'), runStep(3, 'cancelled')],
    });
    expect(keptParts(run)).toEqual({ kept: ['Research', 'Draft'], from: ['Summary'] });
  });

  it('does not keep work the reviewer sent back', () => {
    const run = teamRun(
      [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'revise' }]],
      { status: 'interrupted', ...ENDED },
    );
    expect(keptParts(run)).toEqual({ kept: ['Research'], from: ['Blog post', 'LinkedIn post'] });
  });

  it('lists the steps at work, in run order', () => {
    const run = teamRun([['succeeded'], ['running'], ['running'], ['pending']]);
    expect(runningTitles(run)).toEqual(['Blog post', 'LinkedIn post']);
  });
});

describe('reportModel', () => {
  it('puts it together: deliverables with their roles, the reviewer, progress and outcome', () => {
    const run = teamRun([['succeeded'], ['succeeded'], ['running'], ['pending']]);
    const model = reportModel(run);
    expect(model.deliverables.map(({ title, role, state }) => [title, role, state])).toEqual([
      ['Blog post', 'Writer', 'ready'],
      ['LinkedIn post', 'Writer', 'writing'],
    ]);
    expect(model.reviewer?.step.step_order).toBe(4);
    expect([model.done, model.total, model.outcome]).toEqual([2, 4, 'running']);
  });

  it('does not count work sent back as done', () => {
    const run = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(reportModel(run).done).toBe(1);
  });

  it('has nothing to show for a run with no steps yet', () => {
    const model = reportModel(makeRun({ status: 'queued', started_at: null, steps: [] }));
    expect(model).toEqual({
      deliverables: [],
      reviewer: null,
      done: 0,
      total: 0,
      outcome: 'queued',
    });
  });

  it('reads a step its definition does not describe from its result row', () => {
    // A run whose definition changed shape: step 3 is in the run but not in its snapshot.
    const run = makeRun({
      definition: { name: 'Launch kit', inputs: [], steps: makeRun().definition.steps.slice(0, 2) },
    });
    const summary = stepOf(run, 3);
    expect(definitionOf(run, summary)).toMatchObject({ order: 3, title: 'Summary', role: '' });
    expect(reportModel(run).deliverables.map((view) => view.title)).toEqual(['Draft', 'Summary']);
  });

  it('reads roles and reviews from the definition the run started with', () => {
    const run = teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]);
    expect(reportModel(run).deliverables[0].definition).toBe(TEAM[1]);
  });
});

describe('reportIds', () => {
  it('gives every part of a run’s report its own id', () => {
    const ids = reportIds(7);
    expect([ids.outcome, ids.signOff, ids.deliverable(2), ids.title(2), ids.agent(3)]).toEqual([
      'run-7-outcome',
      'run-7-sign-off',
      'run-7-deliverable-2',
      'run-7-deliverable-2-title',
      'run-7-agent-3',
    ]);
  });
});
