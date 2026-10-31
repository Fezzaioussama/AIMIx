import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { MessageContext } from './messageContext';
import type { QuestionsMessage } from './missionMessages';
import { QuestionsMessageView, SKIP_SAID } from './QuestionsMessageView';

const ASKED: QuestionsMessage = {
  id: 'q1',
  from: 'aimix',
  kind: 'questions',
  state: 'open',
  description: 'Write a report',
  questions: [
    { question: 'Who reads it?', options: ['Students', 'Managers'] },
    { question: 'Which format?', options: ['PDF', 'Slides'] },
  ],
};

function show(message: QuestionsMessage = ASKED, openId: string | null = 'q1') {
  const answerQuestions = vi.fn();
  // The view reads only these two fields of the workspace.
  const context = { openQuestionsId: openId, answerQuestions } as unknown as MessageContext;
  render(<QuestionsMessageView message={message} context={context} />);
  return answerQuestions;
}

describe('QuestionsMessageView', () => {
  it('builds the team from the answers picked, said in words', async () => {
    const user = userEvent.setup();
    const answerQuestions = show();
    const build = screen.getByRole('button', { name: 'Build my team' });

    expect(build).toBeDisabled();
    await user.click(screen.getByRole('radio', { name: 'Students' }));
    await user.click(screen.getByRole('radio', { name: 'Slides' }));
    await user.click(build);

    expect(answerQuestions).toHaveBeenCalledWith(
      ASKED,
      [
        { question: 'Who reads it?', answer: 'Students' },
        { question: 'Which format?', answer: 'Slides' },
      ],
      'Who reads it? — Students\nWhich format? — Slides',
    );
  });

  it('prefers an answer of one’s own, and leaves unanswered questions out', async () => {
    const user = userEvent.setup();
    const answerQuestions = show();

    await user.click(screen.getByRole('radio', { name: 'Students' }));
    await user.type(
      screen.getByRole('textbox', { name: 'Your own answer to: Who reads it?' }),
      'New hires',
    );
    expect(screen.getByRole('radio', { name: 'Students' })).not.toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Build my team' }));

    expect(answerQuestions).toHaveBeenCalledWith(
      ASKED,
      [{ question: 'Who reads it?', answer: 'New hires' }],
      'Who reads it? — New hires',
    );
  });

  it('can skip the questions', async () => {
    const user = userEvent.setup();
    const answerQuestions = show();

    await user.click(screen.getByRole('button', { name: 'Skip' }));

    expect(answerQuestions).toHaveBeenCalledWith(ASKED, [], SKIP_SAID);
  });

  it('shows questions that can no longer be answered as plain text', () => {
    show({ ...ASKED, state: 'skipped' }, null);

    expect(screen.getByText('Who reads it?')).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/Skipped/)).toBeInTheDocument();
  });
});
