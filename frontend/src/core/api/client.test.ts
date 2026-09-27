import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import { ApiError, request } from './client';
import { clearTokens, getAccessToken, saveTokens } from '../auth/tokenStorage';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('api client', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('attaches the bearer token when a session exists', async () => {
    saveTokens({ access: 'token-abc', refresh: 'refresh-abc' });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true }));

    await request(API.models);

    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.get('Authorization')).toBe('Bearer token-abc');
  });

  it('omits the auth header when there is no session', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true }));

    await request(API.models);

    const headers = fetchMock.mock.calls[0][1]?.headers as Headers;
    expect(headers.has('Authorization')).toBe(false);
  });

  it('reads the code and detail from the canonical error contract', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: 'provider_timeout', detail: 'openrouter did not respond.' }, 504),
    );

    await expect(request(API.chat)).rejects.toMatchObject({
      code: 'provider_timeout',
      status: 504,
      message: 'openrouter did not respond.',
    });
  });

  it('falls back to the status line for a body that is not from the API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>502 Bad Gateway</html>', { status: 502 }),
    );

    await expect(request(API.chat)).rejects.toMatchObject({
      code: 'error',
      message: 'Request failed (502)',
    });
  });

  it('tags an unreachable server distinctly from an API error', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'));

    await expect(request(API.models)).rejects.toMatchObject({
      code: 'network_error',
      status: 0,
    });
  });

  it('clears the stored session on a 401 so the guard can redirect', async () => {
    saveTokens({ access: 'stale', refresh: 'stale-refresh' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ error: 'not_authenticated', detail: 'Token expired' }, 401));

    await expect(request(API.pipelines)).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
  });
});
