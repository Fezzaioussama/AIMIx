import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { makeRun, runStep, usageOf } from '../testData';
import { appendix, renderReport, useReportSpec } from './testReport';

const RESEARCH_USED = { input_tokens: 1234, output_tokens: 567, cost_usd: 0.0123 };
const DRAFT_USED = { input_tokens: 100, output_tokens: 20, cost_usd: 0.0004 };

/** A run in flight that has already spent something: step 1 done, step 2 working. */
const spending = makeRun({
  usage: usageOf(1334, 587, 0.0127),
  steps: [
    runStep(1, 'succeeded', 'Research notes', RESEARCH_USED),
    runStep(2, 'running', '', DRAFT_USED),
    runStep(3, 'pending'),
  ],
});

describe('RunReport cost', () => {
  useReportSpec();

  it('shows the running total in the meta line, with its tokens a hover away', () => {
    renderReport(spending);

    expect(screen.getByText('$0.0127')).toHaveAttribute('title', '1,334 tokens in, 587 out');
  });

  it('shows what each agent cost in “How your team got there”', async () => {
    const user = userEvent.setup();
    renderReport(spending);
    await user.click(screen.getByRole('button', { name: /How your team got there/ }));

    expect(within(appendix()).getByText('$0.0123')).toHaveAttribute(
      'title',
      '1,234 tokens in, 567 out',
    );
    expect(within(appendix()).getByText('$0.0004')).toHaveAttribute(
      'title',
      '100 tokens in, 20 out',
    );
  });

  it('shows the spending limit next to the total', () => {
    renderReport({ ...spending, max_cost_usd: 0.5 });

    expect(screen.getByText('of $0.50 limit')).toBeInTheDocument();
  });

  it('says when the cost is unknown for the model', () => {
    renderReport(
      makeRun({
        usage: { ...usageOf(1334, 587, null), cost_complete: false },
        steps: [
          runStep(1, 'succeeded', 'Research notes', { ...RESEARCH_USED, cost_usd: null }),
          runStep(2, 'running'),
          runStep(3, 'pending'),
        ],
      }),
    );

    expect(screen.getAllByText('Cost unknown for this model')[0]).toHaveAttribute(
      'title',
      '1,334 tokens in, 587 out',
    );
  });

  it('calls a cost that is only partly known a floor', () => {
    renderReport(makeRun({ usage: { ...usageOf(1334, 587, 0.0127), cost_complete: false } }));

    expect(screen.getByText('$0.0127 or more')).toBeInTheDocument();
  });

  it('says nothing about cost before a running run has called its model', () => {
    renderReport(makeRun());

    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
    expect(screen.queryByText('No usage recorded')).not.toBeInTheDocument();
  });

  it('shows the limit of a run that has not spent anything yet', () => {
    renderReport(makeRun({ max_cost_usd: 0.5 }));

    expect(screen.getByText('Limit $0.50')).toBeInTheDocument();
  });

  it('says so when a finished run has no usage on record', () => {
    renderReport(
      makeRun({
        status: 'succeeded',
        finished_at: '2026-10-24T10:00:09Z',
        steps: [
          runStep(1, 'succeeded', 'a'),
          runStep(2, 'succeeded', 'b'),
          runStep(3, 'succeeded', 'c'),
        ],
      }),
    );

    expect(screen.getByText('No usage recorded')).toBeInTheDocument();
  });
});

describe('RunReport at its spending limit', () => {
  useReportSpec();

  const atLimit = makeRun({
    status: 'failed',
    finished_at: '2026-10-24T10:00:05Z',
    max_cost_usd: 0.5,
    usage: usageOf(2000, 800, 0.52),
    error: {
      code: 'budget_exceeded',
      detail: 'This run stopped at $0.52 because it reached its $0.50 limit.',
    },
    steps: [
      runStep(1, 'succeeded', 'Research notes', RESEARCH_USED),
      runStep(2, 'failed', '', DRAFT_USED),
      runStep(3, 'cancelled'),
    ],
  });

  it('says it stopped at the limit, in the words the server chose', () => {
    renderReport(atLimit);

    expect(
      screen.getByRole('heading', { level: 3, name: 'The run stopped at its spending limit' }),
    ).toBeVisible();
    expect(
      screen.getByText(
        'This run stopped at $0.52 because it reached its $0.50 limit. Raise the limit below to go on. Resume keeps Research and starts again from Draft and Summary.',
      ),
    ).toBeInTheDocument();
    // The server's words are the sentence: nothing more to fold away.
    expect(screen.queryByRole('button', { name: 'What the service said' })).not.toBeInTheDocument();
  });

  it('keeps the finished work and what the stopped agent spent', async () => {
    const user = userEvent.setup();
    renderReport(atLimit);

    expect(screen.getByText('$0.52')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /How your team got there/ }));
    expect(within(appendix()).getByText('$0.0004')).toBeInTheDocument();
    await user.click(within(appendix()).getByRole('button', { name: /Show what it wrote/ }));
    expect(within(appendix()).getByText('Research notes')).toBeInTheDocument();
  });

  it('asks for a higher limit and resumes under it', async () => {
    const user = userEvent.setup();
    const { control } = renderReport(atLimit);
    const field = screen.getByLabelText('Raise the limit to');
    expect(field).toHaveValue('1.04');

    await user.clear(field);
    await user.type(field, '2');
    await user.click(screen.getByRole('button', { name: 'Resume' }));

    expect(control.resume).toHaveBeenCalledExactlyOnceWith({ max_cost_usd: 2 });
  });

  it('gives the outcome heading the focus once a higher limit has resumed the run', async () => {
    const user = userEvent.setup();
    const { poll } = renderReport(atLimit);

    await user.click(screen.getByRole('button', { name: 'Resume' }));
    poll(makeRun({ max_cost_usd: 2, usage: atLimit.usage }));

    expect(await screen.findByRole('heading', { name: 'Your team is working' })).toHaveFocus();
  });

  it('keeps the plain Resume for a run that failed for another reason', async () => {
    const user = userEvent.setup();
    const { control } = renderReport({
      ...atLimit,
      usage: usageOf(2000, 800, 0.1),
      error: { code: 'provider_timeout', detail: 'The agent timed out.' },
    });

    expect(screen.queryByLabelText('Raise the limit to')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Resume' }));
    expect(control.resume).toHaveBeenCalledExactlyOnceWith(undefined);
  });
});
