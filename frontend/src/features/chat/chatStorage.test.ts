import { beforeEach, describe, expect, it, vi } from 'vitest';

import { forgetChat, readOpenChat, writeOpenChat } from './chatStorage';

const KEY = 'aimix.chat.open.v1';

beforeEach(() => window.sessionStorage.clear());

describe('chatStorage', () => {
  it('keeps which chat is open for the tab', () => {
    writeOpenChat(12);

    expect(readOpenChat()).toBe(12);
    expect(window.sessionStorage.getItem(KEY)).toBe('12');
  });

  it('reads nothing when no chat is open, or what is kept is not an id', () => {
    expect(readOpenChat()).toBeNull();
    window.sessionStorage.setItem(KEY, 'twelve');
    expect(readOpenChat()).toBeNull();
    window.sessionStorage.setItem(KEY, '-3');
    expect(readOpenChat()).toBeNull();
  });

  it('forgets the open chat with the session', () => {
    writeOpenChat(5);

    forgetChat();

    expect(readOpenChat()).toBeNull();
    expect(window.sessionStorage.getItem(KEY)).toBeNull();
  });

  it('still works when the storage is blocked', () => {
    const blocked = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });

    expect(() => writeOpenChat(1)).not.toThrow();
    expect(readOpenChat()).toBeNull();
    blocked.mockRestore();
  });
});
