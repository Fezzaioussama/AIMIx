import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { RunStep } from '../../../core/api/types';
import { FLOW, ENDED, flowRun, runOf, teamRun, TEAM, type StepState } from './reportTestData';
import {
  appendix,
  deliverablesRegion,
  inDeliverables,
  renderReport,
  useReportSpec,
} from './testReport';

const finished = { status: 'succeeded' as const, ...ENDED };
const rounds = (n: number, verdict: RunStep['verdict'] = null) => ({ rounds: n, verdict });

/** The planner's team, finished: both writers and the Orchestrator's check in round `n`. */
function checkedIn(n: number, verdict: RunStep['verdict']): StepState[] {
  return [
    ['succeeded'],
    ['succeeded', rounds(n)],
    ['succeeded', rounds(n)],
    ['succeeded', rounds(n, verdict)],
  ];
}

describe('RunReport: deliverables a condition skipped', () => {
  useReportSpec();

  it('says what a skipped deliverable needed, and that it was skipped', () => {
    renderReport(
      flowRun(
        [['succeeded'], ['succeeded'], ['succeeded', rounds(1, 'pass')], ['skipped']],
        finished,
      ),
    );

    expect(screen.getByRole('heading', { level: 3, name: '1 deliverable ready' })).toBeVisible();
    expect(
      screen.getByText('Done in 4 min 54 s. SEO was skipped because its condition was not met.'),
    ).toBeInTheDocument();
    expect(
      inDeliverables(
        'Not made: its condition was not met. It runs only if the previous result contains “blog”.',
      ),
    ).toBeInTheDocument();
  });

  it('says so when every deliverable was skipped', () => {
    const onlySeo = FLOW.map((step) => ({ ...step, is_output: step.order === 4 }));
    renderReport(
      runOf(
        onlySeo,
        [['succeeded'], ['succeeded'], ['succeeded', rounds(1, 'pass')], ['skipped']],
        finished,
      ),
    );

    expect(
      screen.getByRole('heading', { level: 3, name: 'Done, with no deliverable' }),
    ).toBeVisible();
    expect(inDeliverables(/^Not made: its condition was not met\./)).toBeInTheDocument();
  });
});

describe('RunReport: the check and its rounds', () => {
  useReportSpec();

  it.each([
    ['approved the first time', checkedIn(1, 'pass'), 'Checked and approved by the Orchestrator.'],
    [
      'approved after a round of fixes',
      checkedIn(2, 'pass'),
      'Approved by the Orchestrator after 1 round of fixes.',
    ],
    [
      'approved after two rounds of fixes',
      checkedIn(3, 'pass'),
      'Approved by the Orchestrator after 2 rounds of fixes.',
    ],
    [
      'still asking for fixes when the rounds ran out',
      checkedIn(3, 'revise'),
      'The Orchestrator still asked for fixes after 2 rounds, so the last version was kept. Read the check before you use it.',
    ],
    [
      'without a verdict',
      checkedIn(1, null),
      'The Orchestrator gave no clear verdict, so the work was kept as it is.',
    ],
  ])('signs the work off: %s', (_name, states, line) => {
    renderReport(teamRun(states, finished));

    expect(screen.getByText(line)).toBeInTheDocument();
  });

  it('says the check approved each document, and shows no round the first time', async () => {
    const user = userEvent.setup();
    renderReport(teamRun(checkedIn(1, 'pass'), finished));

    for (const title of ['Blog post', 'LinkedIn post']) {
      const article = screen.getByRole('article', { name: title });
      expect(within(article).getByText('Approved by the Orchestrator')).toBeInTheDocument();
    }
    await user.click(screen.getByRole('button', { name: /How your team got there/ }));
    expect(screen.queryByText(/Round \d/)).not.toBeInTheDocument();
  });

  it('opens the reviewer’s full check from its sign-off, signed with its role', async () => {
    const user = userEvent.setup();
    renderReport(teamRun(checkedIn(1, 'pass'), finished));

    const toggle = screen.getByRole('button', { name: 'Read the full check' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveAccessibleName('Hide the full check');
    expect(screen.getByText('Final check text')).toBeInTheDocument();
    expect(screen.getByText('— Orchestrator')).toBeInTheDocument();
  });

  it('closes a long check from its end and takes you back to its toggle', async () => {
    const user = userEvent.setup();
    const long = 'A finding. '.repeat(200);
    renderReport(
      teamRun(
        [
          ['succeeded'],
          ['succeeded'],
          ['succeeded'],
          ['succeeded', { verdict: 'pass', output: long }],
        ],
        finished,
      ),
    );
    const toggle = screen.getByRole('button', { name: 'Read the full check' });
    await user.click(toggle);

    const panel = document.getElementById('run-7-sign-off-body') as HTMLElement;
    await user.click(within(panel).getByRole('button', { name: 'Hide the full check' }));

    expect(toggle).toHaveFocus();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('shows the work being fixed, round by round', async () => {
    const user = userEvent.setup();
    renderReport(
      teamRun([
        ['succeeded'],
        ['running', rounds(2)],
        ['succeeded'],
        ['succeeded', rounds(1, 'revise')],
      ]),
    );

    expect(
      screen.getByRole('heading', { level: 3, name: 'Fixing what the check found' }),
    ).toBeVisible();
    expect(
      screen.getByText(
        'Your team is working on round 2 of 3. Each deliverable appears below again as soon as it is ready.',
      ),
    ).toBeInTheDocument();
    expect(within(deliverablesRegion()).getAllByText('Being revised · round 2 of 3')).toHaveLength(
      2,
    );
    expect(screen.getByText('The Orchestrator asked for fixes.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Read what needs fixing' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /How your team got there/ }));
    expect(within(appendix()).getAllByText(/Round 2 of 3/).length).toBeGreaterThan(0);
  });

  it('calls a reviewer without a role “the reviewer”', () => {
    const anonymous = TEAM.map((step) => (step.order === 4 ? { ...step, role: '' } : step));
    renderReport(
      runOf(anonymous, [
        ['succeeded'],
        ['running', rounds(2)],
        ['succeeded'],
        ['succeeded', rounds(1, 'revise')],
      ]),
    );

    expect(screen.getByText('The reviewer asked for fixes.')).toBeInTheDocument();
  });

  it('says the work is being checked, on the header and on each document', () => {
    renderReport(teamRun([['succeeded'], ['succeeded'], ['succeeded'], ['running']]));

    expect(
      screen.getByRole('heading', { level: 3, name: 'Your work is being checked' }),
    ).toBeVisible();
    expect(screen.getByText('The Orchestrator is checking the work…')).toBeInTheDocument();
    for (const title of ['Blog post', 'LinkedIn post']) {
      const article = screen.getByRole('article', { name: title });
      expect(within(article).getByText('Being checked by the Orchestrator')).toBeInTheDocument();
    }
  });

  it('says nothing about the check while the run is still on its way to it', () => {
    renderReport(teamRun([['succeeded'], ['running'], ['pending'], ['pending']]));

    expect(screen.queryByText(/Orchestrator (is|asked|gave)|approved by/)).not.toBeInTheDocument();
  });

  it('opens the check from the reviewer’s row in “How your team got there”', async () => {
    const user = userEvent.setup();
    renderReport(teamRun(checkedIn(1, 'pass'), finished));
    await user.click(screen.getByRole('button', { name: /How your team got there/ }));

    await user.click(within(appendix()).getByRole('link', { name: 'Read the check above' }));

    const toggle = screen.getByRole('button', { name: 'Hide the full check' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(toggle).toHaveFocus();
  });
});
