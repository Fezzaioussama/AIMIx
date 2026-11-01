import { beforeEach, describe, expect, it } from 'vitest';

import { forgetChat, MAX_STORED_MESSAGES, readChat, writeChat } from './chatStorage';
import type { ChatMessage } from './useChatStream';

const KEY = 'aimix.chat.v1';

function message(id: number, overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id,
    text: `message ${id}`,
    sender: id % 2 === 0 ? 'ai' : 'user',
    timestamp: new Date('2026-11-01T09:00:00Z'),
    tools: [],
    ...overrides,
  };
}

beforeEach(() => window.sessionStorage.clear());

describe('chatStorage', () => {
  it('keeps the conversation with its dates, tools and failed replies', () => {
    const reply = message(2, {
      failed: true,
      tools: [
        {
          id: '2-0',
          tool: 'design_workflow',
          label: 'Designing your workflow',
          status: 'finished',
          action: { kind: 'pipeline', id: 4, title: 'Digest', subtitle: 'Open the mission' },
        },
      ],
    });
    writeChat([message(1), reply]);

    expect(readChat()).toEqual([message(1), reply]);
  });

  it('shows a tool still running when the chat was left as stopped', () => {
    writeChat([
      message(2, {
        tools: [{ id: '2-0', tool: 'design_workflow', label: 'Designing', status: 'started' }],
      }),
    ]);

    expect(readChat()[0]?.tools[0]).toMatchObject({ status: 'failed', detail: 'Stopped' });
  });

  it('drops what it cannot read instead of failing', () => {
    window.sessionStorage.setItem(
      KEY,
      JSON.stringify([
        { id: 1, text: 'ok', sender: 'user', timestamp: '2026-11-01T09:00:00Z', tools: [] },
        { id: 2, text: 'no date', sender: 'ai', tools: [] },
        { id: 3, text: 'odd sender', sender: 'robot', timestamp: '2026-11-01T09:00:00Z' },
        {
          id: 4,
          text: 'odd link',
          sender: 'ai',
          timestamp: '2026-11-01T09:00:00Z',
          tools: [
            {
              id: '4-0',
              tool: 'x',
              label: 'x',
              status: 'finished',
              action: { kind: 'elsewhere', id: 1, title: 't', subtitle: 's' },
            },
          ],
        },
      ]),
    );

    const restored = readChat();
    expect(restored.map((item) => item.id)).toEqual([1, 4]);
    expect(restored[1]?.tools[0]?.action).toBeUndefined();

    window.sessionStorage.setItem(KEY, '{not json');
    expect(readChat()).toEqual([]);
  });

  it('keeps only the newest messages, and forgets them all on request', () => {
    const many = Array.from({ length: MAX_STORED_MESSAGES + 5 }, (_, index) => message(index + 1));
    writeChat(many);

    expect(readChat()).toHaveLength(MAX_STORED_MESSAGES);
    expect(readChat()[0]?.id).toBe(6);

    forgetChat();
    expect(readChat()).toEqual([]);
  });
});
