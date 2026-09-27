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

  it('maps the backend {error, details} shape to a single message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: 'AI Service not configured', details: 'Key missing.' }, 503),
    );

    await expect(request(API.chat)).rejects.toThrow('AI Service not configured Key missing.');
  });

  it('maps a DRF field error to its first message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ username: ['A user with that username already exists.'] }, 400),
    );

    await expect(request(API.register)).rejects.toThrow(
      'A user with that username already exists.',
    );
  });

  it('clears the stored session on a 401 so the guard can redirect', async () => {
    saveTokens({ access: 'stale', refresh: 'stale-refresh' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ detail: 'Token expired' }, 401));

    await expect(request(API.pipelines)).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
  });
});
