import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { LiveRun } from './LiveRun';
import { PendingApprovals } from './PendingApprovals';
import { makeApproval, makeRun, runStep } from './testData';

/** A run whose second step ("Draft", role "Writer") is stopped at a tool call. */
function waitingRun(...asked: ReturnType<typeof makeApproval>[]) {
  const run = makeRun({
    status: 'waiting',
    steps: [
      runStep(1, 'succeeded', 'Research notes'),
      runStep(2, 'running'),
      runStep(3, 'pending'),
    ],
    pending_approvals: asked,
  });
  run.definition.steps[1] = { ...run.definition.steps[1], role: 'Writer' };
  return run;
}

describe('PendingApprovals', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date('2026-10-24T10:00:30Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('shows no card while nothing waits', () => {
    const { container } = render(<PendingApprovals run={makeRun()} />);

    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(container.textContent).toBe('');
  });

  it('keeps the keyboard in place when the answered card goes away', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const run = waitingRun(makeApproval());
    const { container, rerender } = render(
      <PendingApprovals run={run} onApprove={vi.fn()} onDecline={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: 'Approve' }));
    expect(screen.getByRole('button', { name: 'Approve' })).toHaveFocus();

    rerender(
      <PendingApprovals
        run={{ ...run, status: 'running', pending_approvals: [] }}
        onApprove={vi.fn()}
        onDecline={vi.fn()}
      />,
    );

    // Not back at the top of the page: on the spot where the card was.
    expect(screen.queryByRole('region')).not.toBeInTheDocument();
    expect(document.body).not.toHaveFocus();
    expect(container.firstElementChild).toHaveFocus();
  });

  it('leaves focus alone when it is somewhere else', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const run = waitingRun(makeApproval());
    const { rerender } = render(
      <>
        <button type="button">Elsewhere</button>
        <PendingApprovals run={run} onApprove={vi.fn()} onDecline={vi.fn()} />
      </>,
    );
    await user.click(screen.getByRole('button', { name: 'Elsewhere' }));

    rerender(
      <>
        <button type="button">Elsewhere</button>
        <PendingApprovals run={{ ...run, pending_approvals: [] }} />
      </>,
    );

    expect(screen.getByRole('button', { name: 'Elsewhere' })).toHaveFocus();
  });

  it('names the step and its agent on a card for each request', () => {
    const run = waitingRun(makeApproval(), makeApproval({ id: 32, step_order: 1 }));
    render(<PendingApprovals run={run} onApprove={vi.fn()} onDecline={vi.fn()} />);

    const region = screen.getByRole('region', { name: 'Actions waiting for your approval' });
    expect(screen.getAllByRole('region', { name: 'Allow “Send email”?' })).toHaveLength(2);
    expect(within(region).getByText(/Draft \(Writer\) wants to use this tool/)).toBeVisible();
    expect(within(region).getByText(/Research wants to use this tool/)).toBeVisible();
    expect(screen.getByText('2 actions are waiting for your approval.')).toBeInTheDocument();
  });

  it('answers by the id of the request', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onDecline = vi.fn();
    const run = waitingRun(makeApproval({ id: 31 }), makeApproval({ id: 32 }));
    render(<PendingApprovals run={run} onApprove={onApprove} onDecline={onDecline} />);

    const second = screen.getAllByRole('region', { name: 'Allow “Send email”?' })[1];
    await user.click(within(second).getByRole('button', { name: 'Approve' }));
    const first = screen.getAllByRole('region', { name: 'Allow “Send email”?' })[0];
    await user.click(within(first).getByRole('button', { name: 'Decline' }));

    expect(onApprove).toHaveBeenCalledWith(32);
    expect(onDecline).toHaveBeenCalledWith(31);
  });

  it('shows the requests of a screen that cannot answer them, without buttons', () => {
    render(<PendingApprovals run={waitingRun(makeApproval())} />);

    expect(screen.getByRole('region', { name: 'Allow “Send email”?' })).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('LiveRun waiting for the person', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date('2026-10-24T10:00:30Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('says the run waits for you, offers Stop, and shows what it asks', () => {
    render(
      <LiveRun
        run={waitingRun(makeApproval())}
        onStop={vi.fn()}
        onApprove={vi.fn()}
        onDecline={vi.fn()}
      />,
    );

    expect(screen.getByText('Waiting for you')).toBeInTheDocument();
    expect(
      screen.getByText(
        'This run is waiting for you. Approve or decline the action below to let it go on.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Run waiting for you. 1 of 3 steps done.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeEnabled();
    expect(screen.getByRole('region', { name: 'Allow “Send email”?' })).toBeVisible();
    // Its step is still working, as on the diagram.
    expect(screen.getByRole('button', { name: /Draft, writer, output, Running/ })).toBeDisabled();
  });

  it('hands the answers to whoever shows the run', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const onApprove = vi.fn();
    render(
      <LiveRun
        run={waitingRun(makeApproval({ id: 44 }))}
        onApprove={onApprove}
        onDecline={vi.fn()}
        busy={false}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Approve' }));

    expect(onApprove).toHaveBeenCalledWith(44);
  });
});
