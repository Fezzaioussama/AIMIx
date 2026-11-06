import { describe, expect, it, vi } from 'vitest';

import { streamText } from './client';
import { streamChatReply } from './chat';

vi.mock('./client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./client')>()),
  streamText: vi.fn(),
}));

async function* chunks(...parts: string[]) {
  yield* parts;
}

const CONTEXT = { chatId: 12, timezone: 'Europe/Paris' };

describe('streamChatReply', () => {
  it('decodes NDJSON events split across chunks', async () => {
    vi.mocked(streamText).mockReturnValue(
      chunks(
        '{"type": "text", "text": "Hel',
        'lo"}\n{"type": "tool", "tool": "create_pipeline", "label": "Creating a pipeline", ',
        '"status": "started"}\n',
      ),
    );

    const events = [];
    for await (const event of streamChatReply('hi', CONTEXT)) events.push(event);

    expect(streamText).toHaveBeenCalledWith(
      '/api/chat',
      { prompt: 'hi', chat_id: 12, timezone: 'Europe/Paris' },
      undefined,
      'application/x-ndjson',
    );
    expect(events).toEqual([
      { type: 'text', text: 'Hello' },
      {
        type: 'tool',
        tool: 'create_pipeline',
        label: 'Creating a pipeline',
        status: 'started',
      },
    ]);
  });

  it('sends the message to its chat, which remembers the conversation', async () => {
    vi.mocked(streamText).mockReturnValue(chunks('{"type": "text", "text": "Done."}\n'));

    for await (const event of streamChatReply('Make it weekly', { chatId: 3, timezone: 'UTC' }))
      void event;

    expect(vi.mocked(streamText).mock.lastCall?.[1]).toEqual({
      prompt: 'Make it weekly',
      chat_id: 3,
      timezone: 'UTC',
    });
  });

  it('refuses a line that is not an event', async () => {
    vi.mocked(streamText).mockReturnValue(chunks('not json\n'));

    await expect(async () => {
      for await (const event of streamChatReply('hi', CONTEXT)) void event;
    }).rejects.toThrow('The chat reply could not be read.');
  });
});
