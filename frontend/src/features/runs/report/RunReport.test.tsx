import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { describe, expect, it } from 'vitest';

import type { Run } from '../../../core/api/types';
import { AI_NOTICE } from '../../../core/ui/AiNotice';
import { makeApproval, runStep } from '../testData';
import { defined, ENDED, runOf } from './reportTestData';
import {
  announcer,
  appendix,
  controls,
  deliverablesRegion,
  inDeliverables,
  renderReport,
  teamWithRoles,
  useReportSpec,
} from './testReport';

const going = teamWithRoles();
const queued = teamWithRoles({
  status: 'queued',
  started_at: null,
  steps: [runStep(1, 'pending'), runStep(2, 'pending'), runStep(3, 'pending')],
});
const waiting = teamWithRoles({ status: 'waiting', pending_approvals: [makeApproval()] });
const DRAFT = 'The opening.\n\n## Heading\n\nThe **body**.';
const done = teamWithRoles({
  status: 'succeeded',
  finished_at: '2026-10-24T10:04:54Z',
  steps: [
    runStep(1, 'succeeded', 'Research notes'),
    runStep(2, 'succeeded', DRAFT),
    runStep(3, 'succeeded', 'Summary text'),
  ],
});
/** Stopped with Research done, Draft and Summary not: `fields` says how and why. */
function stopped(fields: Partial<Run>): Run {
  return teamWithRoles({
    finished_at: '2026-10-24T10:00:05Z',
    steps: [
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'failed'),
      runStep(3, 'cancelled'),
    ],
    ...fields,
  });
}
const timedOut = stopped({
  status: 'failed',
  error: { code: 'provider_timeout', detail: 'The agent timed out.' },
});
const KEPT = 'Resume keeps Research and starts again from Draft and Summary.';

function outcome(name: string, level = 3): HTMLElement {
  return screen.getByRole('heading', { level, name });
}

describe('RunReport', () => {
  useReportSpec();

  it('lines a queued run up, with Stop and its deliverables not started', async () => {
    const user = userEvent.setup();
    const { control } = renderReport(queued);

    expect(outcome('Your team is lined up')).toBeInTheDocument();
    expect(screen.getByText('It starts as soon as a slot is free.')).toBeInTheDocument();
    expect(within(deliverablesRegion()).getAllByText('Not started yet')).toHaveLength(2);
    expect(screen.queryByText(AI_NOTICE)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Stop the run' }));
    expect(control.stop).toHaveBeenCalledOnce();
  });

  it('says who is working, and keeps the work in between out of the deliverables', () => {
    const { container } = renderReport(going);

    expect(outcome('Your team is working')).toBeInTheDocument();
    expect(screen.getByText('Now working: Draft. 1 of 3 agents done.')).toBeInTheDocument();
    expect(inDeliverables('Starting…')).toBeInTheDocument();
    expect(within(deliverablesRegion()).queryByText('Research notes')).not.toBeInTheDocument();
    expect(screen.getAllByText(AI_NOTICE)).toHaveLength(1);
    const rule = container.querySelector('[data-look]') as HTMLElement;
    expect(rule).toHaveAttribute('data-look', 'working');
    expect(rule.lastElementChild).toHaveStyle({ transform: 'scaleX(0.3333333333333333)' });
    expect(screen.queryByRole('button', { name: 'Resume' })).not.toBeInTheDocument();
  });

  it('asks for your OK right under the header, and answers by the request’s id', async () => {
    const user = userEvent.setup();
    const { control } = renderReport(waiting);

    const heading = outcome('Your team needs your OK');
    expect(
      screen.getByText(
        'Draft (Writer) wants to use “Send email” from crm. The run waits until you answer below.',
      ),
    ).toBeInTheDocument();
    const asks = screen.getByRole('region', { name: 'Actions waiting for your approval' });
    const header = heading.closest('header') as HTMLElement;
    expect(header.compareDocumentPosition(asks) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      asks.compareDocumentPosition(deliverablesRegion()) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Stop the run' })).toBeEnabled();
    expect(inDeliverables('Waiting for your OK')).toBeInTheDocument();
    expect(
      within(deliverablesRegion()).getByRole('link', { name: 'Review the request' }),
    ).toHaveAttribute('href', '#approval-31');

    await user.click(within(asks).getByRole('button', { name: 'Approve' }));
    expect(control.approve).toHaveBeenCalledWith(31);
  });

  it('hands over a finished run’s deliverables as documents to read, copy and download', async () => {
    const user = userEvent.setup();
    const { container } = renderReport(done);

    expect(outcome('2 deliverables ready')).toBeInTheDocument();
    expect(screen.getByText('Done in 4 min 54 s.')).toBeInTheDocument();
    const nav = screen.getByRole('navigation', { name: 'Deliverables in this result' });
    expect(within(nav).getByRole('link', { name: 'Draft' })).toHaveAttribute(
      'href',
      '#run-7-deliverable-2',
    );
    expect(within(nav).getByRole('link', { name: 'Summary' })).toBeInTheDocument();
    for (const title of ['Draft', 'Summary']) {
      const article = screen.getByRole('article', { name: title });
      expect(within(article).getByRole('heading', { level: 3, name: title })).toBeVisible();
      expect(
        within(article).getByRole('button', { name: `Copy ${title} as formatted text` }),
      ).toBeInTheDocument();
      expect(within(article).getByRole('button', { name: `Download ${title}` })).toBeVisible();
      expect(within(article).getByText(/^by Writer/)).toBeInTheDocument();
    }
    const draft = screen.getByRole('article', { name: 'Draft' });
    // Its text starts at ##: that is its top level, just under the title (no h4 skipped).
    expect(within(draft).getByRole('heading', { level: 4, name: 'Heading' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Stop|Resume/ })).not.toBeInTheDocument();
    expect(container.querySelector('[data-look]')).toHaveAttribute('data-look', 'complete');

    const toggle = screen.getByRole('button', { name: /How your team got there/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(appendix().querySelectorAll('li[id^="run-7-agent-"]')).toHaveLength(3);
  });

  it('jumps from the header to a deliverable and gives its title the focus', async () => {
    const user = userEvent.setup();
    renderReport(done);

    const nav = screen.getByRole('navigation', { name: 'Deliverables in this result' });
    await user.click(within(nav).getByRole('link', { name: 'Summary' }));

    expect(screen.getByRole('heading', { level: 3, name: 'Summary' })).toHaveFocus();
  });

  it('nests every heading one level up under a page’s h1', () => {
    renderReport(done, { level: 2 });

    expect(outcome('2 deliverables ready', 2)).toBeInTheDocument();
    const draft = screen.getByRole('article', { name: 'Draft' });
    expect(within(draft).getByRole('heading', { level: 2, name: 'Draft' })).toBeInTheDocument();
    expect(within(draft).getByRole('heading', { level: 3, name: 'Heading' })).toBeInTheDocument();
  });

  it('offers no jump links for a single deliverable', () => {
    const team = [defined(1, 1, 'Research'), defined(2, 2, 'Blog post', { is_output: true })];
    renderReport(runOf(team, [['succeeded'], ['succeeded']], { status: 'succeeded', ...ENDED }));

    expect(outcome('1 deliverable ready')).toBeInTheDocument();
    expect(
      screen.queryByRole('navigation', { name: 'Deliverables in this result' }),
    ).not.toBeInTheDocument();
  });

  it('explains a failure in plain words, keeps the service’s own, and offers Resume', async () => {
    const user = userEvent.setup();
    const { control, container } = renderReport(timedOut);

    expect(outcome('The run stopped before it finished')).toBeInTheDocument();
    expect(
      screen.getByText(`Draft stopped because the AI service did not answer in time. ${KEPT}`),
    ).toBeInTheDocument();
    const said = screen.getByRole('button', { name: 'What the service said' });
    expect(said).toHaveAttribute('aria-expanded', 'false');
    await user.click(said);
    expect(said).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('The agent timed out.')).toBeInTheDocument();
    expect(
      inDeliverables('Not finished: it stopped because the AI service did not answer in time.'),
    ).toBeInTheDocument();
    expect(inDeliverables('Not finished: the run stopped before it was done.')).toBeInTheDocument();
    expect(container.querySelector('[data-look]')).toHaveAttribute('data-look', 'short');

    await user.click(screen.getByRole('button', { name: 'Resume' }));
    expect(control.resume).toHaveBeenCalledExactlyOnceWith(undefined);
  });

  it('points to Settings when no AI service is set up', () => {
    renderReport(
      stopped({ status: 'failed', error: { code: 'provider_not_configured', detail: 'No key.' } }),
    );

    expect(screen.getByText(/Add an AI service key in Settings, then resume\./)).toBeVisible();
    expect(screen.getByRole('link', { name: 'Open Settings' })).toHaveAttribute(
      'href',
      '/settings',
    );
  });

  it.each([
    ['cancelled', 'You stopped the run', KEPT],
    [
      'interrupted',
      'The run was interrupted',
      `The server restarted while your team was working. ${KEPT}`,
    ],
  ] as const)('tells a run that ended %s what Resume keeps', async (status, heading, sentence) => {
    const user = userEvent.setup();
    const { control } = renderReport(stopped({ status, error: null }));

    expect(outcome(heading)).toBeInTheDocument();
    expect(screen.getByText(sentence)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Resume' }));
    expect(control.resume).toHaveBeenCalledOnce();
  });

  it('reads “Stopping…” while the stop is on its way', async () => {
    const user = userEvent.setup();
    const control = controls({ stop: () => new Promise<void>(() => {}) });
    const { poll } = renderReport(going, { control });

    await user.click(screen.getByRole('button', { name: 'Stop the run' }));
    poll(going, { ...control, busy: true });

    expect(screen.getByRole('button', { name: 'Stopping…' })).toBeDisabled();
  });

  it('gives the outcome heading the focus once Stop has done its work', async () => {
    const user = userEvent.setup();
    const { poll } = renderReport(going);

    await user.click(screen.getByRole('button', { name: 'Stop the run' }));
    poll(stopped({ status: 'cancelled', error: null }));

    expect(await screen.findByRole('heading', { name: 'You stopped the run' })).toHaveFocus();
  });

  it('names the focused heading by the new outcome while the old words still swap out', async () => {
    MotionGlobalConfig.skipAnimations = false;
    try {
      const user = userEvent.setup();
      const { poll } = renderReport(going);

      await user.click(screen.getByRole('button', { name: 'Stop the run' }));
      poll(stopped({ status: 'cancelled', error: null }));

      const heading = screen.getByRole('heading', { level: 3, name: 'You stopped the run' });
      expect(heading).toHaveFocus();
      // The old words are still on their way out (M2), yet the heading already says the new.
      expect(heading).toHaveTextContent('Your team is working');
    } finally {
      MotionGlobalConfig.skipAnimations = true;
    }
  });

  it('leaves the focus alone when a poll changes the run by itself', async () => {
    const { poll } = renderReport(going);

    poll(stopped({ status: 'cancelled', error: null }));

    await screen.findByRole('heading', { name: 'You stopped the run' });
    expect(document.body).toHaveFocus();
  });

  it('says why the last action failed, in the report’s only alert', () => {
    renderReport(going, { control: controls({ error: 'Could not stop this run.' }) });

    const alerts = screen.getAllByRole('alert');
    expect(alerts).toHaveLength(1);
    expect(alerts[0]).toHaveTextContent('Could not stop this run.');
  });

  it('announces what changed between polls, never the run as it first shows', () => {
    const { poll } = renderReport(going);
    expect(announcer()).toHaveTextContent(/^$/);

    poll({ ...done, finished_at: '2026-10-24T10:04:54Z' });

    expect(announcer()).toHaveTextContent('Your team finished: 2 deliverables ready.');
  });

  it('takes what the screen adds: a link to Runs, a note, its actions and the diagram', () => {
    renderReport(timedOut, {
      extras: {
        linkToRuns: true,
        note: 'This run used an earlier version of this pipeline.',
        actions: <button type="button">Delete</button>,
        diagram: true,
      },
    });

    expect(screen.getByRole('link', { name: 'Open in Runs' })).toHaveAttribute('href', '/runs/7');
    expect(
      screen.getByText('This run used an earlier version of this pipeline.'),
    ).toBeInTheDocument();
    const resume = screen.getByRole('button', { name: 'Resume' });
    const extra = screen.getByRole('button', { name: 'Delete' });
    expect(resume.compareDocumentPosition(extra) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(appendix()).getByRole('list', { name: 'Pipeline diagram' })).toBeInTheDocument();
  });

  it('leaves the diagram and the link to Runs out by default', () => {
    renderReport(done);

    expect(screen.queryByRole('link', { name: 'Open in Runs' })).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: 'Pipeline diagram' })).not.toBeInTheDocument();
  });
});
