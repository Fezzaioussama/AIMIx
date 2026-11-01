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

const FRESH = { history: [], timezone: 'Europe/Paris' };

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
    for await (const event of streamChatReply('hi', FRESH)) events.push(event);

    expect(streamText).toHaveBeenCalledWith(
      '/api/chat',
      { prompt: 'hi', history: [], timezone: 'Europe/Paris' },
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

  it('sends the conversation so far with the new message', async () => {
    vi.mocked(streamText).mockReturnValue(chunks('{"type": "text", "text": "Done."}\n'));
    const history = [
      { role: 'user' as const, content: 'Build a news digest' },
      { role: 'assistant' as const, content: 'Built it.' },
    ];

    for await (const event of streamChatReply('Make it weekly', { history, timezone: 'UTC' }))
      void event;

    expect(vi.mocked(streamText).mock.lastCall?.[1]).toEqual({
      prompt: 'Make it weekly',
      history,
      timezone: 'UTC',
    });
  });

  it('refuses a line that is not an event', async () => {
    vi.mocked(streamText).mockReturnValue(chunks('not json\n'));

    await expect(async () => {
      for await (const event of streamChatReply('hi', FRESH)) void event;
    }).rejects.toThrow('The chat reply could not be read.');
  });
});
