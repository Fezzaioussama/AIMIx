import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../api/endpoints';
import { clearTokens, saveTokens } from '../auth/tokenStorage';
import { useAccountName } from './useAccountName';

describe('useAccountName', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    clearTokens();
  });

  it('asks who is signed in once, and gives the username', async () => {
    saveTokens({ access: 'token' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(Response.json({ message: 'Hello', user_id: 3, username: 'alice' }));

    const { result } = renderHook(() => useAccountName());

    await waitFor(() => expect(result.current).toBe('alice'));
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe(API.whoAmI);
  });

  it('stays null when the request fails', async () => {
    saveTokens({ access: 'token' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        Response.json({ error: 'server_error', detail: 'Down.' }, { status: 500 }),
      );

    const { result } = renderHook(() => useAccountName());

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(result.current).toBeNull();
  });

  it('aborts the request when the screen goes away', () => {
    saveTokens({ access: 'token' });
    let signal: AbortSignal | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((_path, init) => {
      signal = init?.signal ?? undefined;
      return new Promise<Response>(() => {});
    });

    const { unmount } = renderHook(() => useAccountName());
    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
