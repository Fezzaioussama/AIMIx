import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApprovalCard } from './ApprovalCard';
import { makeApproval } from './testData';

const QUESTION = makeApproval({
  kind: 'question',
  tool_name: 'ask_user',
  tool_source: 'AIMIx',
  tool_description: '',
  arguments: { question: 'Blue or red?', options: ['Blue', 'Red'] },
});

function renderQuestion(props: Partial<Parameters<typeof ApprovalCard>[0]> = {}) {
  const onAnswer = vi.fn();
  const onDecline = vi.fn();
  const onApprove = vi.fn();
  render(
    <ApprovalCard
      approval={QUESTION}
      askedBy="Draft email (Writer)"
      onApprove={onApprove}
      onDecline={onDecline}
      onAnswer={onAnswer}
      {...props}
    />,
  );
  return { onAnswer, onDecline, onApprove };
}

describe('QuestionCard', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
    vi.setSystemTime(new Date('2026-10-24T10:00:30Z'));
  });
  afterEach(() => vi.useRealTimers());

  it('asks the question, with the suggested answers as buttons', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { onAnswer, onApprove } = renderQuestion();

    const card = screen.getByRole('region', { name: 'Blue or red?' });
    expect(within(card).getByText('Draft email (Writer) asks you.')).toBeInTheDocument();
    expect(within(card).getByText('· No answer counts as skipping it.')).toBeInTheDocument();
    const suggested = within(card).getByRole('group', { name: 'Suggested answers' });
    await user.click(within(suggested).getByRole('button', { name: 'Red' }));

    expect(onAnswer).toHaveBeenCalledWith('Red');
    expect(onApprove).not.toHaveBeenCalled();
  });

  it('sends an answer of their own, trimmed, and skips on request', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { onAnswer, onDecline } = renderQuestion();
    const send = screen.getByRole('button', { name: 'Send answer' });
    expect(send).toBeDisabled();

    await user.type(screen.getByLabelText('Or write your own answer'), '  Green  ');
    await user.click(send);
    await user.click(screen.getByRole('button', { name: 'Skip' }));

    expect(onAnswer).toHaveBeenCalledWith('Green');
    expect(onDecline).toHaveBeenCalledTimes(1);
  });

  it('only shows the question where it cannot be answered', () => {
    renderQuestion({ onAnswer: undefined, onDecline: undefined, onApprove: undefined });

    expect(screen.getByText('Answer it from the run in Runs.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send answer' })).not.toBeInTheDocument();
  });
});
