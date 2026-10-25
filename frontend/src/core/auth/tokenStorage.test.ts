import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearTokens,
  endSession,
  getAccessToken,
  saveTokens,
  subscribeToSessionEnd,
} from './tokenStorage';

describe('token storage', () => {
  afterEach(clearTokens);

  it('keeps the access token in memory instead of browser storage', () => {
    saveTokens({ access: 'short-lived-access' });

    expect(getAccessToken()).toBe('short-lived-access');
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it('ends a session by dropping the token and telling every subscriber', () => {
    const first = vi.fn();
    const second = vi.fn();
    const unsubscribeFirst = subscribeToSessionEnd(first);
    const unsubscribeSecond = subscribeToSessionEnd(second);
    saveTokens({ access: 'token' });

    endSession();

    expect(getAccessToken()).toBeNull();
    expect(first).toHaveBeenCalledOnce();
    expect(second).toHaveBeenCalledOnce();
    unsubscribeFirst();
    unsubscribeSecond();
  });

  it('stops telling a subscriber once it unsubscribes', () => {
    const listener = vi.fn();
    const unsubscribe = subscribeToSessionEnd(listener);

    unsubscribe();
    endSession();

    expect(listener).not.toHaveBeenCalled();
  });
});
