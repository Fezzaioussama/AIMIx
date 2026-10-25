import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { Run } from '../../core/api/types';
import type { FollowedRun } from '../runs/useFollowedRun';
import { RunDetails } from './RunDetails';
import { makeApproval } from '../runs/testData';
import { finishedRun, runningRun } from './testData';

function followedRun(overrides: Partial<FollowedRun> = {}): FollowedRun {
  return {
    run: null,
    error: '',
    busy: false,
    stop: vi.fn().mockResolvedValue(undefined),
    resume: vi.fn().mockResolvedValue(undefined),
    approve: vi.fn().mockResolvedValue(undefined),
    decline: vi.fn().mockResolvedValue(undefined),
    adopt: vi.fn(),
    follow: vi.fn(),
    active: false,
    shown: null,
    shownActive: false,
    shownElapsedMs: null,
    ...overrides,
  };
}

function view(run: Run, followed = followedRun()) {
  return (
    <MemoryRouter>
      <RunDetails run={run} followed={followed} />
    </MemoryRouter>
  );
}

const disclosure = () => screen.getByText('Run details').closest('details') as HTMLDetailsElement;

describe('RunDetails', () => {
  it('is open while the run works and for a run that stopped short', () => {
    const { rerender } = render(view(runningRun()));
    expect(disclosure().open).toBe(true);

    rerender(view(finishedRun({ status: 'failed', error: { code: 'x', detail: 'It broke.' } })));
    expect(disclosure().open).toBe(true);
  });

  it('is folded for a finished run, so the deliverables lead', () => {
    render(view(finishedRun()));

    expect(disclosure().open).toBe(false);
  });

  it('folds by itself when the run is done, and opens again when it is resumed', () => {
    const { rerender } = render(view(runningRun()));

    rerender(view(finishedRun()));
    expect(disclosure().open).toBe(false);

    rerender(view(runningRun()));
    expect(disclosure().open).toBe(true);
  });

  it('keeps the person’s choice while the run stays as it is', async () => {
    const { rerender } = render(view(finishedRun()));

    await userEvent.click(screen.getByText('Run details'));
    rerender(view(finishedRun({ final_output: 'changed' })));

    expect(disclosure().open).toBe(true);
  });

  it('holds the live run, with Stop and a way into the Runs screen', async () => {
    const followed = followedRun();
    render(view(runningRun(), followed));

    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));

    expect(followed.stop).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('link', { name: 'Open in Runs' })).toHaveAttribute('href', '/runs/9');
  });

  it('lets the person answer a tool call the run waits on, right here', async () => {
    const followed = followedRun();
    const waiting = runningRun({
      status: 'waiting',
      pending_approvals: [makeApproval({ id: 31 })],
    });
    const { rerender } = render(view(waiting, followed));

    expect(disclosure().open).toBe(true); // a waiting run is never folded away
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));
    expect(followed.approve).toHaveBeenCalledWith(31);

    rerender(view(waiting, followed));
    await userEvent.click(screen.getByRole('button', { name: 'Decline' }));
    expect(followed.decline).toHaveBeenCalledWith(31);
  });

  it('resumes under the new limit when a run stopped at its spending limit', async () => {
    const followed = followedRun();
    const atLimit = finishedRun({
      status: 'failed',
      error: {
        code: 'budget_exceeded',
        detail: 'This run stopped at $0.50 because it reached its $0.50 limit.',
      },
      max_cost_usd: 0.5,
      usage: { input_tokens: 10, output_tokens: 5, cost_usd: 0.5, cost_complete: true },
    });
    render(view(atLimit, followed));

    const field = screen.getByLabelText(/raise the limit to/i);
    await userEvent.clear(field);
    await userEvent.type(field, '1.25');
    await userEvent.click(screen.getByRole('button', { name: 'Resume' }));

    expect(followed.resume).toHaveBeenCalledWith({ max_cost_usd: 1.25 });
  });
});
