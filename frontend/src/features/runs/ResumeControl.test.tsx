import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ResumeControl } from './ResumeControl';
import { makeRun, runStep, usageOf } from './testData';

const failed = makeRun({
  status: 'failed',
  finished_at: '2026-10-24T10:00:05Z',
  steps: [runStep(1, 'succeeded', 'a'), runStep(2, 'failed'), runStep(3, 'cancelled')],
});

const overLimit = makeRun({
  ...failed,
  max_cost_usd: 0.5,
  usage: usageOf(2000, 800, 0.52),
  error: {
    code: 'budget_exceeded',
    detail: 'This run stopped at $0.52 because it reached its $0.50 limit.',
  },
});

describe('ResumeControl', () => {
  it('resumes at once when the run did not stop at a limit', async () => {
    const onResume = vi.fn();
    render(<ResumeControl run={failed} onResume={onResume} busy={false} />);

    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));

    // No click event passed on as if it were a limit.
    expect(onResume).toHaveBeenCalledExactlyOnceWith();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('keeps its own limit when the run is under it', async () => {
    const underLimit = makeRun({ ...failed, max_cost_usd: 5, usage: usageOf(2000, 800, 0.52) });
    const onResume = vi.fn();
    render(<ResumeControl run={underLimit} onResume={onResume} busy={false} />);

    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));

    expect(onResume).toHaveBeenCalledExactlyOnceWith();
  });

  it('asks for a higher limit when the run stopped at its limit, and says what it has used', () => {
    render(<ResumeControl run={overLimit} onResume={vi.fn()} busy={false} />);

    expect(screen.getByLabelText('Raise the limit to')).toHaveValue('1.00');
    expect(screen.getByText('It has used $0.52 so far.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeEnabled();
  });

  it('resumes under the new limit', async () => {
    const onResume = vi.fn();
    render(<ResumeControl run={overLimit} onResume={onResume} busy={false} />);
    const field = screen.getByLabelText('Raise the limit to');

    await userEvent.clear(field);
    await userEvent.type(field, '$2.50');
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));

    expect(onResume).toHaveBeenCalledExactlyOnceWith({ max_cost_usd: 2.5 });
  });

  it('submits from the keyboard', async () => {
    const onResume = vi.fn();
    render(<ResumeControl run={overLimit} onResume={onResume} busy={false} />);

    await userEvent.type(screen.getByLabelText('Raise the limit to'), '{Enter}');

    expect(onResume).toHaveBeenCalledExactlyOnceWith({ max_cost_usd: 1 });
  });

  it('will not resume under a limit the run has already used up', async () => {
    const onResume = vi.fn();
    render(<ResumeControl run={overLimit} onResume={onResume} busy={false} />);
    const field = screen.getByLabelText('Raise the limit to');

    await userEvent.clear(field);
    await userEvent.type(field, '0.40');

    expect(field).toBeInvalid();
    expect(
      screen.getByText('Enter more than $0.52, what this run has already used.'),
    ).toBeVisible();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();

    await userEvent.type(field, '{Enter}');
    expect(onResume).not.toHaveBeenCalled();
  });

  it('will not resume on something that is not an amount', async () => {
    render(<ResumeControl run={overLimit} onResume={vi.fn()} busy={false} />);
    const field = screen.getByLabelText('Raise the limit to');

    await userEvent.clear(field);
    await userEvent.type(field, 'plenty');

    expect(screen.getByText('Enter an amount above zero, like 1.00.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();
  });

  it('asks for a token limit when that is the one that was reached', async () => {
    const tokenStopped = makeRun({
      ...failed,
      max_cost_usd: null,
      max_tokens: 2000,
      usage: usageOf(1500, 600, null),
    });
    const onResume = vi.fn();
    render(<ResumeControl run={tokenStopped} onResume={onResume} busy={false} />);

    expect(screen.getByLabelText('Raise the token limit to')).toHaveValue('4000');
    expect(screen.getByText('It has used 2,100 tokens so far.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));
    expect(onResume).toHaveBeenCalledExactlyOnceWith({ max_tokens: 4000 });
  });

  it('is not clickable while a stop or resume is in flight', () => {
    const { rerender } = render(<ResumeControl run={failed} onResume={vi.fn()} busy />);
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();

    rerender(<ResumeControl run={overLimit} onResume={vi.fn()} busy />);
    expect(screen.getByRole('button', { name: 'Resume' })).toBeDisabled();
    expect(screen.getByLabelText('Raise the limit to')).toBeDisabled();
  });
});
