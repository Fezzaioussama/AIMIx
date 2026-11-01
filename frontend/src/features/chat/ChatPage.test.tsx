import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../core/api/client';
import { streamChatReply } from '../../core/api/chat';
import { getWebhook } from '../../core/api/webhooks';
import type { ChatEvent } from '../../core/api/chatTypes';
import { ChatPage } from './ChatPage';

vi.mock('../../core/api/chat', () => ({ streamChatReply: vi.fn() }));
vi.mock('../../core/api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/api/webhooks')>()),
  getWebhook: vi.fn(),
}));

async function* events(...items: ChatEvent[]) {
  yield* items;
}

async function* failure(): AsyncGenerator<ChatEvent> {
  yield* [];
  throw new ApiError('The agent timed out.', 504, 'provider_timeout');
}

function renderChat() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

async function say(text: string) {
  await userEvent.type(screen.getByPlaceholderText('Say what you want done…'), text);
  await userEvent.click(screen.getByRole('button', { name: 'Send message' }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  vi.mocked(streamChatReply).mockReset();
});

describe('ChatPage', () => {
  it('fills and focuses the composer when a starter prompt is picked', async () => {
    renderChat();
    await userEvent.click(screen.getByRole('button', { name: /Schedule a run/ }));
    const composer = screen.getByPlaceholderText('Say what you want done…');
    expect(composer).toHaveValue('Run my newest workflow every weekday at 9:00.');
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
    renderChat();

    await say('Schedule it');

    const link = await screen.findByRole('link', { name: /Weekly digest/ });
    expect(link).toHaveAttribute('href', '/schedules');
    expect(await screen.findByText('Scheduled.')).toBeInTheDocument();
  });

  it('links a run it checked to the run screen', async () => {
    vi.mocked(streamChatReply).mockReturnValue(
      events(
        {
          type: 'tool',
          tool: 'get_run',
          label: 'Checking a run',
          status: 'finished',
          action: { kind: 'run', id: 12, title: 'News digest', subtitle: 'Finished' },
        },
        { type: 'text', text: 'It finished.' },
      ),
    );
    renderChat();

    await say('How did my digest go?');

    const link = await screen.findByRole('link', { name: /News digest/ });
    expect(link).toHaveAttribute('href', '/runs/12');
  });

  it('shows a webhook it made as its secret link, read from the server', async () => {
    vi.mocked(getWebhook).mockResolvedValue({
      id: 4,
      pipeline_id: 9,
      pipeline_name: 'News digest',
      enabled: true,
      last_called_at: null,
      last_error: null,
      token: 'tok-456',
    });
    vi.mocked(streamChatReply).mockReturnValue(
      events(
        {
          type: 'tool',
          tool: 'create_webhook',
          label: 'Making a webhook link',
          status: 'finished',
          action: { kind: 'webhook', id: 4, title: 'News digest', subtitle: 'Webhook on' },
        },
        { type: 'text', text: 'Here is its link.' },
      ),
    );
    renderChat();

    await say('Let my form start the digest');

    const url = `${window.location.origin}/api/hooks/tok-456`;
    expect(await screen.findByText(url)).toBeInTheDocument();
    expect(vi.mocked(getWebhook).mock.calls[0]?.[0]).toBe(4);
  });

  it('sends the conversation so far, and the time zone, with a follow-up', async () => {
    vi.mocked(streamChatReply)
      .mockReturnValueOnce(events({ type: 'text', text: 'Built: News digest.' }))
      .mockReturnValueOnce(events({ type: 'text', text: 'Scheduled.' }));
    renderChat();

    await say('Build a news digest');
    await screen.findByText('Built: News digest.');
    await say('Make it weekly');
    await screen.findByText('Scheduled.');

    const [prompt, context] = vi.mocked(streamChatReply).mock.calls[1] ?? [];
    expect(prompt).toBe('Make it weekly');
    expect(context?.history).toEqual([
      { role: 'user', content: 'Build a news digest' },
      { role: 'assistant', content: 'Built: News digest.' },
    ]);
    expect(context?.timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
  });

  it('keeps a failed reply on screen but out of what the assistant is told', async () => {
    vi.mocked(streamChatReply)
      .mockReturnValueOnce(failure())
      .mockReturnValueOnce(events({ type: 'text', text: 'Done.' }));
    renderChat();

    await say('Build a news digest');
    expect(await screen.findByText('The agent timed out.')).toBeInTheDocument();
    await say('Try again');
    await screen.findByText('Done.');

    const context = vi.mocked(streamChatReply).mock.calls[1]?.[1];
    expect(context?.history).toEqual([{ role: 'user', content: 'Build a news digest' }]);
  });

  it('continues the conversation after leaving the screen, until a new chat', async () => {
    vi.mocked(streamChatReply).mockReturnValue(events({ type: 'text', text: 'Built it.' }));
    const first = renderChat();
    await say('Build a news digest');
    await screen.findByText('Built it.');
    first.unmount();

    renderChat();
    expect(screen.getByText('Build a news digest')).toBeInTheDocument();
    expect(screen.getByText('Built it.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'New chat' }));
    expect(screen.queryByText('Build a news digest')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Build a workflow/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'New chat' })).not.toBeInTheDocument();
  });
});
