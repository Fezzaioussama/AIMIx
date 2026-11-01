import { beforeEach, describe, expect, it } from 'vitest';

import { you } from './missionMessages';
import { missionKey, readMission, writeMission } from './missionStorage';

/**
 * What a kept conversation may hold of the documents its messages carried (missionShape):
 * their names and sizes, written by this version or missing in an older one.
 */
describe('stored messages with documents', () => {
  beforeEach(() => window.sessionStorage.clear());

  it('keeps only the names and sizes of the documents a message carried', () => {
    const said = you('Summarise these', [{ name: 'report.pdf', pages: 2, characters: 13 }]);

    writeMission(missionKey(7), { messages: [said], draft: null });

    const stored = window.sessionStorage.getItem(missionKey(7)) ?? '';
    expect(JSON.parse(stored).messages[0]).toEqual({
      id: said.id,
      from: 'you',
      text: 'Summarise these',
      documents: [{ name: 'report.pdf', pages: 2, characters: 13 }],
    });
    // A message without documents is written as it always was.
    expect(you('hi')).not.toHaveProperty('documents');
  });

  it('still reads a conversation kept before messages carried documents', () => {
    window.sessionStorage.setItem(
      missionKey(7),
      JSON.stringify({ messages: [{ id: 'old', from: 'you', text: 'kept' }], draft: null }),
    );

    expect(readMission(missionKey(7)).messages).toEqual([{ id: 'old', from: 'you', text: 'kept' }]);
  });

  it('drops a message whose documents are not what the screen draws', () => {
    const damaged: unknown[] = [
      { id: 'a', from: 'you', text: 'x', documents: 'report.pdf' },
      {
        id: 'b',
        from: 'you',
        text: 'x',
        documents: [{ name: 'r.pdf', pages: 'two', characters: 1 }],
      },
      { id: 'c', from: 'you', text: 'x', documents: [{ name: 'r.pdf', pages: null }] },
      { id: 'd', from: 'you', text: 'x', documents: [{ pages: null, characters: 1 }] },
      { id: 'e', from: 'you', text: 'kept', documents: [] },
    ];
    window.sessionStorage.setItem(
      missionKey(7),
      JSON.stringify({ messages: damaged, draft: null }),
    );

    expect(readMission(missionKey(7)).messages.map((message) => message.id)).toEqual(['e']);
  });
});
