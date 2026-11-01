import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionGlobalConfig } from 'motion/react';
import { useState } from 'react';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

import type { Run } from '../../../core/api/types';
import { FOCUS_RING } from '../../../core/ui/focus';
import { makeApproval } from '../testData';
import { reportIds, reportModel } from './reportModel';
import { ENDED, stepOf, teamRun, type StepState } from './reportTestData';
import { TeamWork } from './TeamWork';

beforeAll(() => {
  MotionGlobalConfig.skipAnimations = true;
});
afterAll(() => {
  MotionGlobalConfig.skipAnimations = false;
});
afterEach(() => vi.restoreAllMocks());

interface Options {
  diagram?: boolean;
  onReadCheck?: () => void;
  level?: 2 | 3;
}

/** The appendix with its own open state, as RunReport keeps it. */
function Appendix({
  run,
  diagram = false,
  onReadCheck = () => {},
  level = 3,
}: Options & { run: Run }) {
  const [open, setOpen] = useState(false);
  return (
    <TeamWork
      run={run}
      model={reportModel(run)}
      level={level}
      open={open}
      onToggle={() => setOpen((shown) => !shown)}
      diagram={diagram}
      onReadCheck={onReadCheck}
    />
  );
}

async function renderOpen(run: Run, options: Options = {}) {
  const user = userEvent.setup();
  const view = render(<Appendix run={run} {...options} />);
  await user.click(toggle());
  return { ...view, user };
}

function toggle(): HTMLElement {
  return screen.getByRole('button', { name: /How your team got there/ });
}

function row(title: string): HTMLElement {
  const rows = screen.getAllByRole('listitem');
  const found = rows.find((item) => item.querySelector('p')?.textContent?.startsWith(title));
  if (found === undefined) throw new Error(`No row for ${title}.`);
  return found;
}

const DONE: StepState[] = [
  ['succeeded', { cost_usd: 0.0123, input_tokens: 1234, output_tokens: 567 }],
  ['succeeded'],
  ['succeeded'],
  ['succeeded', { verdict: 'pass' }],
];

function finished(states: StepState[] = DONE): Run {
  return teamRun(states, { status: 'succeeded', ...ENDED });
}

describe('TeamWork', () => {
  it('starts folded, with how many agents and stages the team had', async () => {
    const user = userEvent.setup();
    render(<Appendix run={finished()} />);

    expect(screen.getByRole('heading', { level: 3, name: /How your team got there/ }));
    expect(toggle()).toHaveAccessibleName('How your team got there, 4 agents · 3 stages');
    expect(toggle()).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle());

    expect(toggle()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('heading', { level: 4, name: 'What each agent did' }));
  });

  it('lists every agent in run order, saying when a stage worked at once', async () => {
    await renderOpen(finished());

    const titles = screen
      .getAllByRole('listitem')
      .map((item) => item.querySelector('p')?.firstChild?.textContent);
    expect(titles).toEqual(['Research', 'Blog post', 'LinkedIn post', 'Final check']);
    expect(
      screen.getAllByText(/^Stage \d · at the same time$/).map((cap) => cap.textContent),
    ).toEqual(['Stage 2 · at the same time']);
  });

  it('says what each agent did, its model, cost and tools', async () => {
    const run = finished();
    stepOf(run, 1).tool_calls = [
      { name: 'current_datetime', status: 'success' },
      { name: 'web_search', status: 'success' },
      { name: 'fetch_url', status: 'error' },
    ];

    await renderOpen(run);

    const research = row('Research');
    expect(research).toHaveTextContent('Research · by Researcher');
    expect(within(research).getByText('$0.0123')).toHaveAttribute(
      'title',
      '1,234 tokens in, 567 out',
    );
    expect(research).toHaveTextContent('Done · 4.0 s · $0.0123');
    expect(within(research).getByText('Model: writer')).toBeInTheDocument();
    expect(
      within(research).getByText('1 date check · 1 web search · 1 page read, 1 failed'),
    ).toBeInTheDocument();
    expect(research.querySelector('svg')).toHaveClass('text-emerald-300');
  });

  it('ticks the time of a working agent, and its round in a review loop', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-24T10:00:05Z'));
    const run = teamRun([
      ['succeeded'],
      ['running', { rounds: 2, finished_at: null }],
      ['succeeded', { rounds: 2 }],
      ['succeeded', { verdict: 'revise' }],
    ]);

    await renderOpen(run);

    const blog = row('Blog post');
    expect(blog).toHaveTextContent('Working on round 2 of 3 · 5.0 s');
    expect(within(blog).getByText('Model: writer · Round 2 of 3')).toBeInTheDocument();
    expect(blog.querySelector('svg')).toHaveClass('motion-safe:animate-spin');
  });

  it('says an agent waits for your OK', async () => {
    const run = teamRun([['succeeded'], ['running'], ['pending'], ['pending']], {
      status: 'waiting',
      pending_approvals: [makeApproval({ step_order: 2 })],
    });

    await renderOpen(run);

    expect(row('Blog post')).toHaveTextContent('Waiting for your OK');
    expect(row('Blog post').querySelector('svg')).toHaveClass('text-amber-300');
  });

  it('links a deliverable’s row up to its document, giving its title the focus', async () => {
    const run = finished();
    const ids = reportIds(run.id);
    const { user } = await renderOpen(run);
    render(
      <h3 id={ids.title(2)} tabIndex={-1}>
        Blog post
      </h3>,
    );

    const link = within(row('Blog post')).getByRole('link', { name: 'Read it above' });
    expect(link).toHaveAttribute('href', `#${ids.deliverable(2)}`);
    await user.click(link);

    expect(screen.getByRole('heading', { level: 3, name: 'Blog post' })).toHaveFocus();
  });

  it('offers no way up to a deliverable that is being revised: there is nothing to read yet', async () => {
    // The check sent the writers back; their rows still hold round 1 until they restart.
    const run = teamRun([
      ['succeeded'],
      ['succeeded'],
      ['succeeded'],
      ['succeeded', { verdict: 'revise' }],
    ]);

    await renderOpen(run);

    expect(screen.queryByRole('link', { name: 'Read it above' })).not.toBeInTheDocument();
    for (const writer of ['Blog post', 'LinkedIn post']) {
      expect(within(row(writer)).queryByRole('button')).not.toBeInTheDocument();
    }
  });

  it('links the check’s row to the full check above', async () => {
    const onReadCheck = vi.fn();
    const run = finished();
    const { user } = await renderOpen(run, { onReadCheck });

    const link = within(row('Final check')).getByRole('link', { name: 'Read the check above' });
    expect(link).toHaveAttribute('href', `#${reportIds(run.id).signOff}`);
    await user.click(link);

    expect(onReadCheck).toHaveBeenCalledTimes(1);
  });

  it('folds the team’s own work under its row, its headings nested below', async () => {
    const run = finished();
    stepOf(run, 1).output = '# Findings\n\nShops keep regulars.';
    const { user } = await renderOpen(run);

    const show = within(row('Research')).getByRole('button', { name: 'Show what it wrote' });
    expect(show).toHaveAttribute('aria-expanded', 'false');
    await user.click(show);

    expect(show).toHaveAttribute('aria-expanded', 'true');
    expect(show).toHaveAccessibleName('Hide what it wrote');
    expect(
      within(row('Research')).getByRole('heading', { level: 5, name: 'Findings' }),
    ).toBeInTheDocument();
    // Short: no second "Hide" at its end.
    expect(
      within(row('Research')).getAllByRole('button', { name: 'Hide what it wrote' }),
    ).toHaveLength(1);
  });

  it('closes a long text from its end, giving the focus back to its toggle', async () => {
    const run = finished();
    stepOf(run, 1).output = 'Shops keep regulars. '.repeat(100);
    const { user } = await renderOpen(run);
    const show = within(row('Research')).getByRole('button', { name: 'Show what it wrote' });
    await user.click(show);

    const hides = within(row('Research')).getAllByRole('button', { name: 'Hide what it wrote' });
    expect(hides).toHaveLength(2);
    // jsdom has no scrollIntoView: record which element the jump brings into view.
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = function (this: Element) {
      scrolled(this);
    };
    try {
      await user.click(hides[1]);
    } finally {
      Reflect.deleteProperty(Element.prototype, 'scrollIntoView');
    }

    expect(show).toHaveFocus();
    expect(show).toHaveAttribute('aria-expanded', 'false');
    // The toggle itself, not its row: a row taller than the screen is "in view" already,
    // and would leave the focused toggle above it.
    expect(scrolled).toHaveBeenCalledExactlyOnceWith(show);
  });

  it('lists what the team was given, only when it was given something', async () => {
    const { unmount } = await renderOpen(finished());
    expect(screen.getByRole('heading', { level: 4, name: 'What your team was given' }));
    expect(screen.getByRole('group', { name: 'Your description' })).toHaveTextContent('topic');
    unmount();

    await renderOpen(teamRun(DONE, { status: 'succeeded', ...ENDED, input: '' }));
    expect(screen.queryByRole('heading', { name: 'What your team was given' })).toBeNull();
  });

  it('draws the team’s diagram only where asked to', async () => {
    const { unmount } = await renderOpen(finished());
    expect(screen.queryByRole('list', { name: 'Pipeline diagram' })).toBeNull();
    unmount();

    await renderOpen(finished(), { diagram: true, level: 2 });

    expect(screen.getByRole('heading', { level: 3, name: 'The team' })).toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Pipeline diagram' })).toBeInTheDocument();
    // Read-only, it holds nothing to focus: its scroller takes the keyboard instead.
    const scroller = screen.getByRole('group', { name: 'Team diagram' });
    expect(scroller).toHaveAttribute('tabindex', '0');
    expect(scroller).toHaveClass(...FOCUS_RING.split(' '));
  });
});
