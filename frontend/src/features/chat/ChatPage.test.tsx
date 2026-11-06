import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../../core/api/client';
import { streamChatReply } from '../../core/api/chat';
import { createChat, deleteChat, getChat, listChats, renameChat } from '../../core/api/chats';
import type { ChatDetail, ChatEvent, ChatSummary } from '../../core/api/chatTypes';
import { getWebhook } from '../../core/api/webhooks';
import { ChatPage } from './ChatPage';

vi.mock('../../core/api/chat', () => ({ streamChatReply: vi.fn() }));
vi.mock('../../core/api/chats', () => ({
  listChats: vi.fn(),
  createChat: vi.fn(),
  getChat: vi.fn(),
  renameChat: vi.fn(),
  deleteChat: vi.fn(),
}));
vi.mock('../../core/api/webhooks', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../core/api/webhooks')>()),
  getWebhook: vi.fn(),
}));

const NOTHING = { input_tokens: 0, output_tokens: 0, cost_usd: null, cost_complete: true };

function chat(id: number, title = ''): ChatSummary {
  return { id, title, created_at: '2026-11-06T09:00:00Z', updated_at: '2026-11-06T09:05:00Z' };
}

function detail(summary: ChatSummary, messages: ChatDetail['messages'] = []): ChatDetail {
  return { ...summary, messages, usage: NOTHING };
}

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

/** The header's "New chat", apart from the list's. */
function headerNewChat() {
  return within(screen.getByRole('banner')).queryByRole('button', { name: 'New chat' });
}

function chatList() {
  return within(screen.getByRole('navigation', { name: 'Your chats' }));
}

beforeEach(() => {
  window.sessionStorage.clear();
  vi.mocked(streamChatReply).mockReset();
  vi.mocked(listChats).mockReset().mockResolvedValue([]);
  vi.mocked(createChat).mockReset().mockResolvedValue(chat(1));
  vi.mocked(getChat)
    .mockReset()
    .mockResolvedValue(detail(chat(1)));
  vi.mocked(renameChat).mockReset();
  vi.mocked(deleteChat).mockReset();
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

  it('makes the chat on the server at the first message and sends the rest to it', async () => {
    vi.mocked(streamChatReply)
      .mockReturnValueOnce(events({ type: 'text', text: 'Built: News digest.' }))
      .mockReturnValueOnce(events({ type: 'text', text: 'Scheduled.' }));
    renderChat();

    await say('Build a news digest');
    await screen.findByText('Built: News digest.');
    await say('Make it weekly');
    await screen.findByText('Scheduled.');

    expect(createChat).toHaveBeenCalledTimes(1);
    const calls = vi.mocked(streamChatReply).mock.calls;
    expect(calls.map(([prompt, context]) => [prompt, context.chatId])).toEqual([
      ['Build a news digest', 1],
      ['Make it weekly', 1],
    ]);
    expect(calls[1]?.[1].timezone).toBe(Intl.DateTimeFormat().resolvedOptions().timeZone);
    // The list is read again once a reply ends: the chat has a title and a newer time now.
    expect(listChats).toHaveBeenCalledTimes(3);
  });

  it('adds up what the replies used in the header', async () => {
    const usage = { input_tokens: 120, output_tokens: 30, cost_usd: 0.0123, cost_complete: true };
    vi.mocked(streamChatReply).mockReturnValue(
      events({ type: 'text', text: 'Done.' }, { type: 'usage', usage }),
    );
    renderChat();

    await say('Build a news digest');
    await screen.findByText('Done.');

    expect(await within(screen.getByRole('banner')).findByText('$0.0123')).toBeInTheDocument();
  });

  it('keeps a failed reply on screen and goes on in the same chat', async () => {
    vi.mocked(streamChatReply)
      .mockReturnValueOnce(failure())
      .mockReturnValueOnce(events({ type: 'text', text: 'Done.' }));
    renderChat();

    await say('Build a news digest');
    expect(await screen.findByText('The agent timed out.')).toBeInTheDocument();
    await say('Try again');
    await screen.findByText('Done.');

    expect(createChat).toHaveBeenCalledTimes(1);
    expect(vi.mocked(streamChatReply).mock.calls[1]?.[1].chatId).toBe(1);
  });

  it('fails the reply when the chat cannot be made', async () => {
    vi.mocked(createChat).mockRejectedValue(
      new ApiError('You can keep up to 200 chats. Delete one first.', 400, 'validation_error'),
    );
    renderChat();

    await say('Build a news digest');

    expect(
      await screen.findByText('You can keep up to 200 chats. Delete one first.'),
    ).toBeInTheDocument();
    expect(streamChatReply).not.toHaveBeenCalled();
  });

  it('reopens the open chat after leaving the screen, until a new chat', async () => {
    vi.mocked(streamChatReply).mockReturnValue(events({ type: 'text', text: 'Built it.' }));
    vi.mocked(getChat).mockResolvedValue(
      detail(chat(1, 'Build a news digest'), [
        {
          id: 10,
          role: 'user',
          text: 'Build a news digest',
          tools: [],
          created_at: '2026-11-06T09:04:00Z',
          usage: NOTHING,
        },
        {
          id: 11,
          role: 'assistant',
          text: 'Built it.',
          tools: [],
          created_at: '2026-11-06T09:05:00Z',
          usage: NOTHING,
        },
      ]),
    );
    const first = renderChat();
    await say('Build a news digest');
    await screen.findByText('Built it.');
    first.unmount();

    renderChat();
    expect(await screen.findByText('Built it.')).toBeInTheDocument();
    expect(screen.getByText('Build a news digest')).toBeInTheDocument();
    expect(getChat).toHaveBeenCalledWith(1, expect.any(AbortSignal));

    await userEvent.click(headerNewChat() as HTMLElement);
    expect(screen.queryByText('Build a news digest')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Build a workflow/ })).toBeInTheDocument();
    expect(headerNewChat()).toBeNull();
    expect(window.sessionStorage.getItem('aimix.chat.open.v1')).toBeNull();
  });

  it('lists the chats and opens one from the list', async () => {
    vi.mocked(listChats).mockResolvedValue([chat(3, 'Weekly digest'), chat(2, 'Pictures')]);
    vi.mocked(getChat).mockResolvedValue(
      detail(chat(3, 'Weekly digest'), [
        {
          id: 30,
          role: 'assistant',
          text: 'Here is your digest.',
          tools: [],
          created_at: '2026-11-06T09:05:00Z',
          usage: NOTHING,
        },
      ]),
    );
    renderChat();

    await userEvent.click(await chatList().findByRole('button', { name: /^Weekly digest/ }));

    expect(await screen.findByText('Here is your digest.')).toBeInTheDocument();
    expect(getChat).toHaveBeenCalledWith(3, expect.any(AbortSignal));
    expect(chatList().getByRole('button', { name: /^Weekly digest/ })).toHaveAttribute(
      'aria-current',
      'true',
    );
    expect(within(screen.getByRole('banner')).getByText(/Weekly digest/)).toBeInTheDocument();
  });

  it('renames and deletes a chat from the list', async () => {
    vi.mocked(listChats).mockResolvedValue([chat(3, 'Weekly digest')]);
    vi.mocked(renameChat).mockResolvedValue(chat(3, 'Digest'));
    vi.mocked(deleteChat).mockResolvedValue();
    renderChat();

    await userEvent.click(await chatList().findByRole('button', { name: 'Rename Weekly digest' }));
    const field = screen.getByRole('textbox', { name: 'Chat title' });
    await userEvent.clear(field);
    await userEvent.type(field, 'Digest{Enter}');

    expect(renameChat).toHaveBeenCalledWith(3, 'Digest');
    expect(await chatList().findByRole('button', { name: /^Digest/ })).toBeInTheDocument();

    await userEvent.click(chatList().getByRole('button', { name: 'Delete Digest' }));
    await userEvent.click(chatList().getByRole('button', { name: 'Delete' }));

    expect(deleteChat).toHaveBeenCalledWith(3);
    expect(chatList().queryByRole('button', { name: /^Digest/ })).not.toBeInTheDocument();
  });

  it('says why the chats could not be listed', async () => {
    vi.mocked(listChats).mockRejectedValue(new ApiError('Request failed (500)', 500, 'error'));
    renderChat();

    expect(await chatList().findByRole('alert')).toHaveTextContent('Request failed (500)');
  });
});
