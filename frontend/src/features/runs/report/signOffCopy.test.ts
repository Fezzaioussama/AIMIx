import { describe, expect, it } from 'vitest';

import type { Run, RunStatus } from '../../../core/api/types';
import { makeRun } from '../testData';
import { reportModel, reviewerOf, type DeliverableView } from './reportModel';
import { defined, ENDED, flowRun, runOf, TEAM, teamRun, type StepState } from './reportTestData';
import {
  bylineCheck,
  reviewerName,
  reviewerNameAtStart,
  signOff,
  type SignOffTone,
} from './signOffCopy';

const FULL = { open: 'Read the full check', close: 'Hide the full check' };
const FIXES = { open: 'Read what needs fixing', close: 'Hide what needs fixing' };

/** The team's run with its writers done, its final check in `check`, the run in `status`. */
function checked(check: StepState, status: RunStatus = 'succeeded', writers = 1): Run {
  const writer: StepState = ['succeeded', { rounds: writers }];
  return teamRun([['succeeded'], writer, writer, check], {
    status,
    ...(status === 'running' ? {} : ENDED),
  });
}

const signOffOf = (run: Run) => signOff(reviewerOf(run), run);

describe('signOff', () => {
  it.each<[string, Run, SignOffTone, string]>([
    [
      'approved the first time',
      checked(['succeeded', { verdict: 'pass' }]),
      'approved',
      'Checked and approved by the Orchestrator.',
    ],
    [
      'approved after 1 round of fixes',
      checked(['succeeded', { rounds: 2, verdict: 'pass' }], 'succeeded', 2),
      'approved',
      'Approved by the Orchestrator after 1 round of fixes.',
    ],
    [
      'approved after 2 rounds of fixes',
      checked(['succeeded', { rounds: 3, verdict: 'pass' }], 'succeeded', 3),
      'approved',
      'Approved by the Orchestrator after 2 rounds of fixes.',
    ],
    [
      'still asked for fixes at the limit',
      checked(['succeeded', { rounds: 3, verdict: 'revise' }], 'succeeded', 3),
      'concern',
      'The Orchestrator still asked for fixes after 2 rounds, so the last version was kept. Read the check before you use it.',
    ],
    [
      'no verdict the first time',
      checked(['succeeded', { verdict: null }]),
      'concern',
      'The Orchestrator gave no clear verdict, so the work was kept as it is.',
    ],
    [
      'no verdict after a round of fixes',
      checked(['succeeded', { rounds: 2, verdict: null }], 'succeeded', 2),
      'concern',
      'The Orchestrator gave no clear verdict, so the work was kept as it is.',
    ],
  ])('%s', (_name, run, tone, line) => {
    expect(signOffOf(run)).toMatchObject({ tone, line, toggle: FULL });
  });

  it('says the reviewer asked for fixes while the work goes back', () => {
    const run = checked(['succeeded', { verdict: 'revise' }], 'running');
    expect(signOffOf(run)).toEqual({
      key: 'fixes-1',
      tone: 'fixes',
      line: 'The Orchestrator asked for fixes.',
      toggle: FIXES,
    });
  });

  it('says the reviewer is checking the work, then the revised work', () => {
    expect(signOffOf(checked(['running'], 'running'))).toEqual({
      key: 'checking-1',
      tone: 'checking',
      line: 'The Orchestrator is checking the work…',
      toggle: null,
    });
    expect(signOffOf(checked(['running', { rounds: 2 }], 'running', 2))).toMatchObject({
      line: 'The Orchestrator is checking the revised work…',
    });
  });

  it.each<[string, Run, string]>([
    [
      'the run stopped before the check',
      checked(['pending'], 'cancelled'),
      'Not checked: the run stopped before the Orchestrator could check the work.',
    ],
    [
      'the run stopped during the check',
      checked(['cancelled'], 'cancelled'),
      'Not checked: the run stopped before the Orchestrator could check the work.',
    ],
    [
      'the reviewer failed',
      checked(['failed'], 'failed'),
      'Not checked: the Orchestrator stopped because the AI service did not answer in time.',
    ],
    [
      'the check was skipped',
      checked(['skipped']),
      'Not checked: the check was skipped because its condition was not met.',
    ],
  ])('not checked: %s', (_name, run, line) => {
    expect(signOffOf(run)).toEqual({ key: 'notChecked-1', tone: 'notChecked', line, toggle: null });
  });

  it('keeps what needed fixing readable when the run stopped during the fixes', () => {
    const run = checked(['succeeded', { verdict: 'revise' }], 'cancelled');
    expect(signOffOf(run)).toMatchObject({
      tone: 'notChecked',
      line: 'Not checked: the run stopped before the Orchestrator could check the work.',
      toggle: FIXES,
    });
  });

  it('says nothing while the check is still ahead in an active run', () => {
    expect(signOffOf(checked(['pending'], 'running'))).toBeNull();
  });

  it('says nothing without a reviewer', () => {
    expect(signOffOf(makeRun())).toBeNull();
    expect(signOff(null, makeRun())).toBeNull();
  });

  it('calls a reviewer without a role “the reviewer”', () => {
    const run = teamRun(
      [['succeeded'], ['succeeded'], ['succeeded'], ['succeeded', { verdict: 'revise' }]],
      {
        definition: {
          name: 'Launch',
          inputs: [],
          steps: TEAM.map((step) => ({ ...step, role: '' })),
        },
      },
    );
    expect(signOffOf(run)?.line).toBe('The reviewer asked for fixes.');
  });

  it('has no toggle while the reviewer wrote nothing', () => {
    expect(signOffOf(checked(['succeeded', { verdict: 'pass', output: '  ' }]))?.toggle).toBeNull();
  });
});

describe('reviewerName', () => {
  it('names the reviewer by its role, or “the reviewer”', () => {
    expect(reviewerName({ role: 'Orchestrator' })).toBe('the Orchestrator');
    expect(reviewerName({ role: ' ' })).toBe('the reviewer');
    expect(reviewerNameAtStart({ role: 'Orchestrator' })).toBe('The Orchestrator');
    expect(reviewerNameAtStart({ role: '' })).toBe('The reviewer');
  });
});

describe('bylineCheck', () => {
  /** The check on a deliverable's byline: Blog post (order 2) unless `order` says. */
  function bylineOf(run: Run, order = 2) {
    const model = reportModel(run);
    const view = model.deliverables.find((item) => item.step.step_order === order);
    return bylineCheck(model.reviewer, view as DeliverableView, run);
  }

  it.each<[string, Run, string, SignOffTone]>([
    [
      'approved',
      checked(['succeeded', { verdict: 'pass' }]),
      'Approved by the Orchestrator',
      'approved',
    ],
    [
      'approved after fixes',
      checked(['succeeded', { rounds: 2, verdict: 'pass' }], 'succeeded', 2),
      'Approved by the Orchestrator after fixes',
      'approved',
    ],
    [
      'still asked for fixes',
      checked(['succeeded', { rounds: 3, verdict: 'revise' }], 'succeeded', 3),
      'The Orchestrator still asked for fixes',
      'concern',
    ],
    [
      'no clear verdict',
      checked(['succeeded', { verdict: null }]),
      'No clear verdict from the Orchestrator',
      'concern',
    ],
    [
      'being checked',
      checked(['running'], 'running'),
      'Being checked by the Orchestrator',
      'checking',
    ],
    ['not checked yet', checked(['pending'], 'running'), 'Not checked yet', 'notChecked'],
    [
      'the run stopped',
      checked(['pending'], 'cancelled'),
      'Not checked: the run stopped',
      'notChecked',
    ],
    [
      'the reviewer failed',
      checked(['failed'], 'failed'),
      'Not checked: the run stopped',
      'notChecked',
    ],
    [
      'the check was skipped',
      checked(['skipped']),
      'Not checked: the check was skipped',
      'notChecked',
    ],
  ])('%s', (_name, run, words, tone) => {
    expect(bylineOf(run)).toEqual({ words, tone });
  });

  it('says a parallel writer’s new round waits for the check', () => {
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2 }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);
    expect(bylineOf(run, 3)).toEqual({
      words: 'Revised, waiting for the Orchestrator’s check',
      tone: 'fixes',
    });
  });

  it('says the run stopped when the revised work never got its check', () => {
    const run = teamRun(
      [
        ['succeeded'],
        ['succeeded', { rounds: 2 }],
        ['succeeded', { rounds: 2 }],
        ['succeeded', { verdict: 'revise' }],
      ],
      { status: 'cancelled', ...ENDED },
    );
    expect(bylineOf(run)).toEqual({ words: 'Not checked: the run stopped', tone: 'notChecked' });
  });

  it('has nothing to say for a slot', () => {
    const run = teamRun([['succeeded'], ['running'], ['succeeded'], ['pending']]);
    expect(bylineOf(run, 2)).toBeNull();
    expect(bylineOf(run, 3)).toEqual({ words: 'Not checked yet', tone: 'notChecked' });
  });

  it('has nothing to say for a deliverable after the reviewer’s stage', () => {
    const run = flowRun(
      [['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }], ['succeeded']],
      { status: 'succeeded', ...ENDED },
    );
    expect(bylineOf(run, 2)).toEqual({ words: 'Approved by the reviewer', tone: 'approved' });
    expect(bylineOf(run, 4)).toBeNull();
  });

  it('has nothing to say for a deliverable in the reviewer’s own stage', () => {
    const team = [
      ...TEAM.slice(0, 3),
      defined(4, 3, 'Final check', {
        role: 'Orchestrator',
        is_output: true,
        review: { send_back_to_stage: 2, max_rounds: 2 },
      }),
      defined(5, 3, 'Summary', { is_output: true }),
    ];
    const run = runOf(
      team,
      [
        ['succeeded'],
        ['succeeded'],
        ['succeeded'],
        ['succeeded', { verdict: 'pass' }],
        ['succeeded'],
      ],
      { status: 'succeeded', ...ENDED },
    );
    expect(bylineOf(run, 2)).toEqual({ words: 'Approved by the Orchestrator', tone: 'approved' });
    expect(bylineOf(run, 5)).toBeNull();
  });

  it('has nothing to say for a deliverable the reviewer never reads (before its loop)', () => {
    // The reviewer reads the stage just before its own and its loop's earlier deliverables
    // (StepNode._work and loops._loop on the server), never a stage before the loop.
    const team = [
      defined(1, 1, 'Research brief', { is_output: true }),
      defined(2, 2, 'Blog post', { is_output: true }),
      defined(3, 3, 'Final check', {
        role: 'Orchestrator',
        review: { send_back_to_stage: 2, max_rounds: 2 },
      }),
    ];
    const run = runOf(team, [['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }]], {
      status: 'succeeded',
      ...ENDED,
    });
    expect(bylineOf(run, 1)).toBeNull();
    expect(bylineOf(run, 2)).toEqual({ words: 'Approved by the Orchestrator', tone: 'approved' });
  });

  it('credits the last reviewer only with the deliverables of its own loop', () => {
    const team = [
      defined(1, 1, 'Research brief', { is_output: true }),
      defined(2, 2, 'First check', { review: { send_back_to_stage: 1, max_rounds: 1 } }),
      defined(3, 3, 'Blog post', { is_output: true }),
      defined(4, 4, 'Final check', {
        role: 'Orchestrator',
        review: { send_back_to_stage: 3, max_rounds: 1 },
      }),
    ];
    const pass: StepState = ['succeeded', { verdict: 'pass' }];
    const run = runOf(team, [['succeeded'], pass, ['succeeded'], pass], {
      status: 'succeeded',
      ...ENDED,
    });
    expect(bylineOf(run, 1)).toBeNull();
    expect(bylineOf(run, 3)).toEqual({ words: 'Approved by the Orchestrator', tone: 'approved' });
  });

  it('has nothing to say without a reviewer', () => {
    const run = makeRun({ status: 'succeeded', ...ENDED });
    const model = reportModel(run);
    expect(bylineCheck(model.reviewer, model.deliverables[0], run)).toBeNull();
  });
});
