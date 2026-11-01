import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { Run } from '../../../core/api/types';
import { makeApproval } from '../testData';
import { DeliverableSlot } from './DeliverableSlot';
import { reportModel } from './reportModel';
import { ENDED, flowRun, teamRun, type StepState } from './reportTestData';

beforeAll(() => {
  MotionGlobalConfig.skipAnimations = true;
});
afterAll(() => {
  MotionGlobalConfig.skipAnimations = false;
});
afterEach(() => vi.restoreAllMocks());

/** The slot of `run`'s deliverable titled `title`, rendered alone. */
function renderSlot(run: Run, title = 'LinkedIn post') {
  const slot = (shown: Run) => {
    const view = reportModel(shown).deliverables.find((item) => item.title === title);
    if (view === undefined) throw new Error(`No deliverable ${title}.`);
    return <DeliverableSlot run={shown} view={view} level={3} />;
  };
  const rendered = render(slot(run));
  return { ...rendered, poll: (next: Run) => rendered.rerender(slot(next)) };
}

function article(name = 'LinkedIn post'): HTMLElement {
  return screen.getByRole('article', { name });
}

/** The three still bars that stand where the text will be. */
function bars(): Element | null {
  return article().querySelector('[aria-hidden="true"].space-y-2');
}

const RESEARCHING: StepState[] = [['running'], ['pending'], ['pending'], ['pending']];
const WRITING: StepState[] = [['succeeded'], ['succeeded'], ['running'], ['pending']];

describe('DeliverableSlot', () => {
  it('stands where the document will land: its title, who makes it, what it waits for', () => {
    renderSlot(teamRun(RESEARCHING));

    expect(within(article()).getByRole('heading', { level: 3, name: 'LinkedIn post' }));
    expect(within(article()).getByText('by Writer')).toBeInTheDocument();
    expect(within(article()).getByText('Starts when Research is done')).toBeInTheDocument();
    expect(article()).toHaveClass('border-dashed');
    expect(bars()).not.toBeNull();
  });

  it('says it has not started while the run is queued', () => {
    renderSlot(teamRun([['pending'], ['pending'], ['pending'], ['pending']], { status: 'queued' }));

    expect(within(article()).getByText('Not started yet')).toBeInTheDocument();
  });

  it('shimmers while being written, with the time it has taken so far', () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-24T10:00:05Z'));

    renderSlot(teamRun(WRITING));

    const words = within(article()).getByText('Being written');
    expect(words.parentElement).toHaveClass('motion-safe:animate-shine', 'text-slate-300/80');
    expect(within(article()).getByText('· 5.0 s')).toHaveClass('tabular-nums');
  });

  it('swaps its words in place when the agent starts', async () => {
    const { poll } = renderSlot(teamRun(RESEARCHING));
    const shine = within(article()).getByText('Starts when Research is done').parentElement;

    poll(teamRun(WRITING));

    expect(await within(article()).findByText('Being written')).toBeInTheDocument();
    // The same shimmer holds the new words: nothing was mounted again.
    expect(within(article()).getByText('Being written').parentElement).toBe(shine);
  });

  it('points to the request its agent waits on, and takes the focus there', async () => {
    const user = userEvent.setup();
    const run = teamRun(WRITING, {
      status: 'waiting',
      pending_approvals: [makeApproval({ id: 31, step_order: 3 })],
    });
    render(
      <h3 id="approval-31" tabIndex={-1}>
        Allow “Send email”?
      </h3>,
    );
    renderSlot(run);

    expect(within(article()).getByText('Waiting for your OK')).toBeInTheDocument();
    // It is not writing while it waits: no time ticks beside the words.
    expect(within(article()).queryByText(/^· \d/)).toBeNull();
    const link = within(article()).getByRole('link', { name: 'Review the request' });
    expect(link).toHaveAttribute('href', '#approval-31');

    await user.click(link);

    expect(screen.getByRole('heading', { name: 'Allow “Send email”?' })).toHaveFocus();
  });

  it('says why it never came, quietly and without bars, when the run failed', () => {
    const run = teamRun([['succeeded'], ['succeeded'], ['failed'], ['pending']], {
      status: 'failed',
      ...ENDED,
    });

    renderSlot(run);

    const words = within(article()).getByText(
      'Not finished: it stopped because the AI service did not answer in time.',
    );
    expect(words).toHaveClass('text-slate-400');
    expect(bars()).toBeNull();
    expect(article().querySelector('svg')).toHaveClass('text-amber-300');
  });

  it('says a stopped run left it unfinished', () => {
    renderSlot(
      teamRun([['succeeded'], ['succeeded'], ['cancelled'], ['pending']], {
        status: 'cancelled',
        ...ENDED,
      }),
    );

    expect(
      within(article()).getByText('Not finished: you stopped the run before it was done.'),
    ).toBeInTheDocument();
    expect(bars()).toBeNull();
  });

  it('says a skipped deliverable was not made, and the condition it needed', () => {
    const run = flowRun(
      [['succeeded'], ['succeeded'], ['succeeded', { verdict: 'pass' }], ['skipped']],
      { status: 'succeeded', ...ENDED },
    );

    renderSlot(run, 'SEO');

    expect(
      within(article('SEO')).getByText(
        'Not made: its condition was not met. It runs only if the previous result contains “blog”.',
      ),
    ).toBeInTheDocument();
    expect(article('SEO').querySelector('[aria-hidden="true"].space-y-2')).toBeNull();
  });
});
