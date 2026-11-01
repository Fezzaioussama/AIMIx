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
    for await (const event of streamChatReply('hi')) events.push(event);

    expect(streamText).toHaveBeenCalledWith(
      '/api/chat',
      { prompt: 'hi' },
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

  it('refuses a line that is not an event', async () => {
    vi.mocked(streamText).mockReturnValue(chunks('not json\n'));

    await expect(async () => {
      for await (const event of streamChatReply('hi')) void event;
    }).rejects.toThrow('The chat reply could not be read.');
  });
});
