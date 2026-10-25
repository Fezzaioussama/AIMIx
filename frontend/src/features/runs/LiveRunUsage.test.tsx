import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { LiveRun } from './LiveRun';
import { makeRun, runStep, usageOf } from './testData';

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

describe('LiveRun cost', () => {
  it('shows the running total in the status bar, with its tokens a hover away', () => {
    render(<LiveRun run={spending} />);

    const total = screen.getByText('$0.0127');
    expect(total).toHaveAttribute('title', '1,334 tokens in, 587 out');
    expect(total.closest('div')).toHaveTextContent('1 of 3 steps done');
  });

  it('shows what each step cost, as soon as it has spent anything', () => {
    render(<LiveRun run={spending} />);

    expect(screen.getByText('$0.0123')).toHaveAttribute('title', '1,234 tokens in, 567 out');
    expect(screen.getByText('$0.0004')).toHaveAttribute('title', '100 tokens in, 20 out');
    // Nothing is shown for a step that has not called its model yet.
    expect(screen.getAllByText(/^\$\d/)).toHaveLength(3);
  });

  it('shows the spending limit next to the total', () => {
    render(<LiveRun run={{ ...spending, max_cost_usd: 0.5 }} />);

    expect(screen.getByText('of $0.50 limit')).toBeInTheDocument();
  });

  it('says when the cost is unknown for the model, and keeps the tokens', () => {
    const unknown = makeRun({
      usage: { ...usageOf(1334, 587, null), cost_complete: false },
      steps: [
        runStep(1, 'succeeded', 'Research notes', { ...RESEARCH_USED, cost_usd: null }),
        runStep(2, 'running'),
        runStep(3, 'pending'),
      ],
    });
    render(<LiveRun run={unknown} />);

    const notes = screen.getAllByText('Cost unknown for this model');
    expect(notes).toHaveLength(2);
    expect(notes[0]).toHaveAttribute('title', '1,334 tokens in, 587 out');
  });

  it('calls a cost that is only partly known a floor', () => {
    const partial = makeRun({
      usage: { ...usageOf(1334, 587, 0.0127), cost_complete: false },
      steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'running'), runStep(3, 'pending')],
    });
    render(<LiveRun run={partial} />);

    expect(screen.getByText('$0.0127 or more')).toBeInTheDocument();
  });

  it('shows nothing about cost before a running run has called its model', () => {
    render(<LiveRun run={makeRun()} />);

    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
    expect(screen.queryByText('No usage recorded')).not.toBeInTheDocument();
  });

  it('shows the limit of a run that has not spent anything yet', () => {
    render(<LiveRun run={makeRun({ max_cost_usd: 0.5 })} />);

    expect(screen.getByText('Limit $0.50')).toBeInTheDocument();
  });

  it('says so when a finished run has no usage on record', () => {
    const old = makeRun({
      status: 'succeeded',
      finished_at: '2026-10-24T10:00:09Z',
      steps: [
        runStep(1, 'succeeded', 'a'),
        runStep(2, 'succeeded', 'b'),
        runStep(3, 'succeeded', 'c'),
      ],
    });
    render(<LiveRun run={old} />);

    expect(screen.getByText('No usage recorded')).toBeInTheDocument();
  });
});

describe('LiveRun at its spending limit', () => {
  const stopped = makeRun({
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
    render(<LiveRun run={stopped} onResume={vi.fn()} />);

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Spending limit reached. This run stopped at $0.52 because it reached its $0.50 limit.',
    );
    expect(screen.queryByText(/Draft failed/)).not.toBeInTheDocument();
  });

  it('keeps the finished work and what was spent on the step it stopped', async () => {
    render(<LiveRun run={stopped} onResume={vi.fn()} />);

    expect(screen.getByText('$0.52')).toBeInTheDocument();
    // A finished run opens on its outputs; every step, spend included, is one tab away.
    await userEvent.click(screen.getByRole('tab', { name: 'All steps (3)' }));
    expect(screen.getByText('$0.0004')).toBeInTheDocument();
    expect(screen.getByText('Research notes')).toBeInTheDocument();
  });

  it('asks for a higher limit and resumes under it', async () => {
    const onResume = vi.fn();
    render(<LiveRun run={stopped} onResume={onResume} />);
    const field = screen.getByLabelText('Raise the limit to');
    expect(field).toHaveValue('1.00');

    await userEvent.clear(field);
    await userEvent.type(field, '2');
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));

    expect(onResume).toHaveBeenCalledExactlyOnceWith({ max_cost_usd: 2 });
  });

  it('keeps the plain Resume button for a run that failed for another reason', async () => {
    const onResume = vi.fn();
    const timedOut = makeRun({
      status: 'failed',
      max_cost_usd: 0.5,
      usage: usageOf(2000, 800, 0.1),
      error: { code: 'provider_timeout', detail: 'The agent timed out.' },
      steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'failed'), runStep(3, 'cancelled')],
    });
    render(<LiveRun run={timedOut} onResume={onResume} />);

    expect(screen.getByRole('alert')).toHaveTextContent('Draft failed. The agent timed out.');
    expect(screen.queryByLabelText('Raise the limit to')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(onResume).toHaveBeenCalledExactlyOnceWith();
  });
});
