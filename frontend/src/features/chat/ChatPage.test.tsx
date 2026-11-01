import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { streamChatReply } from '../../core/api/chat';
import type { ChatEvent } from '../../core/api/chatTypes';
import { ChatPage } from './ChatPage';

vi.mock('../../core/api/chat', () => ({ streamChatReply: vi.fn() }));

async function* events(...items: ChatEvent[]) {
  yield* items;
}

describe('ChatPage', () => {
  it('fills and focuses the composer when a starter prompt is picked', async () => {
    render(<ChatPage />);
    await userEvent.click(screen.getByRole('button', { name: /Schedule a run/ }));
    const composer = screen.getByPlaceholderText('Ask anything…');
    expect(composer).toHaveValue(
      'Schedule my newest pipeline every weekday at 09:00 in Europe/Paris.',
    );
    expect(composer).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Send message' })).toBeEnabled();
  });

  it('shows the tool it used and links to what it created', async () => {
    vi.mocked(streamChatReply).mockReturnValue(
      events(
        {
          type: 'tool',
          tool: 'create_schedule',
          label: 'Creating a schedule',
          status: 'started',
        },
        {
          type: 'tool',
          tool: 'create_schedule',
          label: 'Creating a schedule',
          status: 'finished',
          action: {
            kind: 'schedule',
            id: 7,
            title: 'Weekly digest',
            subtitle: 'Daily at 09:00',
          },
        },
        { type: 'text', text: 'Scheduled.' },
      ),
    );
    render(
      <MemoryRouter>
        <ChatPage />
      </MemoryRouter>,
    );

    await userEvent.type(screen.getByPlaceholderText('Ask anything…'), 'Schedule it');
    await userEvent.click(screen.getByRole('button', { name: 'Send message' }));

    const link = await screen.findByRole('link', { name: /Weekly digest/ });
    expect(link).toHaveAttribute('href', '/schedules');
    expect(await screen.findByText('Scheduled.')).toBeInTheDocument();
  });
});
