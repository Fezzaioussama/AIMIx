import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import { ApiError, request, requestBlob, streamText } from './client';
import {
  clearTokens,
  getAccessToken,
  saveTokens,
  subscribeToSessionEnd,
} from '../auth/tokenStorage';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('api client', () => {
  let unsubscribe = (): void => {};

  afterEach(() => {
    unsubscribe();
    unsubscribe = () => {};
    clearTokens();
    vi.restoreAllMocks();
  });

  it('attaches the bearer token when a session exists', async () => {
    saveTokens({ access: 'token-abc' });
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
    saveTokens({ access: 'stale' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: 'not_authenticated', detail: 'Token expired' }, 401),
    );

    await expect(request(API.pipelines)).rejects.toBeInstanceOf(ApiError);
    expect(getAccessToken()).toBeNull();
  });

  it('ends the session, so the screens sign out, when the server refuses the refresh', async () => {
    saveTokens({ access: 'stale' });
    const ended = vi.fn();
    unsubscribe = subscribeToSessionEnd(ended);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: 'not_authenticated', detail: 'Token expired' }, 401),
    );

    await expect(request(API.pipelines)).rejects.toMatchObject({ status: 401 });
    expect(ended).toHaveBeenCalledOnce();
  });

  it('ends the session when even a refreshed token is refused', async () => {
    saveTokens({ access: 'stale' });
    const ended = vi.fn();
    unsubscribe = subscribeToSessionEnd(ended);
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ error: 'not_authenticated', detail: 'Expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ access: 'fresh' }))
      .mockResolvedValueOnce(jsonResponse({ error: 'not_authenticated', detail: 'Gone' }, 401));

    await expect(request(API.pipelines)).rejects.toMatchObject({ status: 401 });
    expect(ended).toHaveBeenCalledOnce();
    expect(getAccessToken()).toBeNull();
  });

  it('ends the session when a chat stream’s refresh is refused', async () => {
    const ended = vi.fn();
    unsubscribe = subscribeToSessionEnd(ended);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ error: 'not_authenticated', detail: 'Token expired' }, 401),
    );

    await expect(streamText(API.chat, { prompt: 'hi' }).next()).rejects.toBeInstanceOf(ApiError);
    expect(ended).toHaveBeenCalledOnce();
  });

  it('keeps the session through a refresh that fails for another reason', async () => {
    const ended = vi.fn();
    unsubscribe = subscribeToSessionEnd(ended);
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ error: 'not_authenticated', detail: 'Expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ error: 'error', detail: 'Unavailable' }, 503));

    await expect(request(API.pipelines)).rejects.toMatchObject({ status: 503 });
    expect(ended).not.toHaveBeenCalled();
  });

  it('does not take a refused sign-in for the end of a session', async () => {
    const ended = vi.fn();
    unsubscribe = subscribeToSessionEnd(ended);
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ error: 'not_authenticated', detail: 'Wrong' }, 401));

    await expect(
      request(API.login, { method: 'POST', body: { username: 'a', password: 'b' } }),
    ).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(ended).not.toHaveBeenCalled();
  });

  it('sends a FormData as multipart, leaving the Content-Type to the browser', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true }));
    const form = new FormData();
    form.append('file', new File(['hi'], 'a.txt'));

    await request(API.extractDocument, { method: 'POST', body: form });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.body).toBe(form);
    expect((init?.headers as Headers).has('Content-Type')).toBe(false);
  });

  it('still sends JSON as JSON', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({ ok: true }));

    await request(API.chat, { method: 'POST', body: { message: 'hi' } });

    const init = fetchMock.mock.calls[0][1];
    expect(init?.body).toBe('{"message":"hi"}');
    expect((init?.headers as Headers).get('Content-Type')).toBe('application/json');
  });

  it('fetches a download like any call: refreshed once on a 401, then read as a Blob', async () => {
    saveTokens({ access: 'stale' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse({ error: 'not_authenticated', detail: 'Expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ access: 'fresh' }))
      .mockResolvedValueOnce(new Response('file body', { status: 200 }));

    const content = await requestBlob(API.file('notes.txt'));

    expect(content.size).toBe('file body'.length);
    expect(fetchMock.mock.calls[1][0]).toBe(API.refresh);
    const retried = fetchMock.mock.calls[2][1]?.headers as Headers;
    expect(retried.get('Authorization')).toBe('Bearer fresh');
  });

  it('reports a caller-cancelled request as cancelled, not as a network failure', async () => {
    const controller = new AbortController();
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
      controller.abort();
      throw new DOMException('Aborted', 'AbortError');
    });

    await expect(request(API.models, { signal: controller.signal })).rejects.toMatchObject({
      code: 'aborted',
    });
  });
});
