import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApprovalCard } from './ApprovalCard';
import { makeApproval } from './testData';

function renderCard(props: Partial<Parameters<typeof ApprovalCard>[0]> = {}) {
  const onApprove = vi.fn();
  const onDecline = vi.fn();
  render(
    <ApprovalCard
      approval={makeApproval()}
      askedBy="Draft email (Writer)"
      onApprove={onApprove}
      onDecline={onDecline}
      {...props}
    />,
  );
  return { onApprove, onDecline };
}

describe('ApprovalCard', () => {
  beforeEach(() => {
    // Thirty seconds into the minute the request was given.
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date('2026-10-24T10:00:30Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('says who asks, for which tool, from where, and what it will use', () => {
    renderCard();

    const card = screen.getByRole('region', { name: 'Allow “Send email”?' });
    expect(within(card).getByText('Needs your OK')).toBeInTheDocument();
    expect(
      within(card).getByText('Draft email (Writer) wants to use this tool from crm.'),
    ).toBeInTheDocument();
    expect(within(card).getByText('Send an email to a contact.')).toBeInTheDocument();
    const used = within(card).getByRole('group', { name: 'What the action will use' });
    expect(within(used).getByText('to')).toBeInTheDocument();
    expect(within(used).getByText('ada@example.com')).toBeInTheDocument();
    expect(within(used).getByText('Launch')).toBeInTheDocument();
  });

  it('counts the time left down', async () => {
    renderCard();
    expect(screen.getByText('30 s left')).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(10_000);

    expect(screen.getByText('20 s left')).toBeInTheDocument();
  });

  it('says when the time is up', async () => {
    renderCard();

    await vi.advanceTimersByTimeAsync(31_000);

    expect(screen.getByText('Time is up')).toBeInTheDocument();
  });

  it('needs no source for a built-in tool', () => {
    renderCard({ approval: makeApproval({ tool_name: 'save_artifact', tool_source: 'AIMIx' }) });

    expect(screen.getByRole('region', { name: 'Allow “Save artifact”?' })).toBeInTheDocument();
    expect(screen.getByText('Draft email (Writer) wants to use this tool.')).toBeInTheDocument();
  });

  it('folds a long value behind Show all and opens it in full', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const body = `Hello Ada. ${'This is the long body of the message. '.repeat(10)}Goodbye.`;
    renderCard({ approval: makeApproval({ arguments: { to: 'ada@example.com', body } }) });

    const summary = screen.getByText('Show all');
    expect(screen.queryByText(body)).not.toBeVisible();
    await user.click(summary);

    expect(screen.getByText(body)).toBeVisible();
    expect(screen.getByText('Show less')).toBeVisible();
  });

  it('says when long values are shortened', () => {
    renderCard({ approval: makeApproval({ arguments_truncated: true }) });

    expect(
      screen.getByText('Long values are shortened here. The tool uses them in full.'),
    ).toBeInTheDocument();
  });

  it('says so when the tool uses nothing else', () => {
    renderCard({ approval: makeApproval({ arguments: {} }) });

    expect(screen.getByText('It uses nothing else.')).toBeInTheDocument();
  });

  it('answers with Approve or Decline', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const { onApprove, onDecline } = renderCard();

    await user.click(screen.getByRole('button', { name: 'Approve' }));
    await user.click(screen.getByRole('button', { name: 'Decline' }));

    expect(onApprove).toHaveBeenCalledOnce();
    expect(onDecline).toHaveBeenCalledOnce();
    expect(screen.getByText('No answer counts as a decline.')).toBeInTheDocument();
  });

  it('shows which answer is on its way and blocks both meanwhile', async () => {
    vi.useRealTimers();
    const user = userEvent.setup();
    const handlers = { onApprove: vi.fn(), onDecline: vi.fn() };
    const view = render(
      <ApprovalCard approval={makeApproval()} askedBy="Step 2" busy={false} {...handlers} />,
    );
    await user.click(screen.getByRole('button', { name: 'Decline' }));

    view.rerender(
      <ApprovalCard approval={makeApproval()} askedBy="Step 2" busy={true} {...handlers} />,
    );

    expect(screen.getByRole('button', { name: 'Declining…' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  });

  it('cannot be answered where the screen gave no way to', () => {
    renderCard({ onApprove: undefined, onDecline: undefined });

    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Decline' })).not.toBeInTheDocument();
    expect(screen.getByText('Answer it from the run in Runs.')).toBeInTheDocument();
  });
});
