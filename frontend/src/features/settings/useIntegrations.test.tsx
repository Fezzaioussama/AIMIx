import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { INTEGRATION, json } from './testData';
import { useIntegrations } from './useIntegrations';

const TOOLS = [{ name: 'crm_search', description: 'Find a contact.' }];

async function loaded(first: Response) {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(first);
  const hook = renderHook(() => useIntegrations());
  await waitFor(() => expect(hook.result.current.status).toBe('idle'));
  return { fetchMock, ...hook };
}

describe('useIntegrations', () => {
  afterEach(() => vi.restoreAllMocks());

  it('adds an integration and closes the form', async () => {
    const { fetchMock, result } = await loaded(json([]));
    fetchMock.mockResolvedValueOnce(json(INTEGRATION, 201));

    act(() => result.current.actions.startEditing('new'));
    expect(result.current.editing).toBe('new');
    const draft = {
      name: 'crm',
      url: INTEGRATION.url,
      headers: [{ name: 'Authorization', value: 'Bearer key-1234', saved: null }],
    };
    await act(() => result.current.actions.create(draft));

    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe(API.integrations);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({
      name: 'crm',
      url: INTEGRATION.url,
      headers: [{ name: 'Authorization', value: 'Bearer key-1234' }],
    });
    expect(result.current.integrations).toEqual([INTEGRATION]);
    expect(result.current.editing).toBeNull();
    expect(result.current.notice?.kind).toBe('success');
  });

  it('turns an integration off and deletes it', async () => {
    const { fetchMock, result } = await loaded(json([INTEGRATION]));
    fetchMock
      .mockResolvedValueOnce(json({ ...INTEGRATION, enabled: false }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await act(() => result.current.actions.setEnabled(INTEGRATION, false));
    expect(fetchMock.mock.calls[1][0]).toBe(API.integration(INTEGRATION.id));
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PATCH');
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ enabled: false });
    expect(result.current.integrations?.[0].enabled).toBe(false);

    await act(() => result.current.actions.remove(INTEGRATION));
    expect(fetchMock.mock.calls[2][1]?.method).toBe('DELETE');
    expect(result.current.integrations).toEqual([]);
  });

  it('keeps each connection test result, passed or failed', async () => {
    const { fetchMock, result } = await loaded(json([INTEGRATION]));
    fetchMock
      .mockResolvedValueOnce(json({ tools: TOOLS }))
      .mockResolvedValueOnce(
        json({ error: 'tool_unavailable', detail: 'Could not connect to crm: it timed out.' }, 502),
      );

    await act(() => result.current.actions.test(INTEGRATION));
    expect(fetchMock.mock.calls[1][0]).toBe(API.testIntegration(INTEGRATION.id));
    expect(result.current.tests[INTEGRATION.id]).toEqual({ status: 'passed', tools: TOOLS });

    await act(() => result.current.actions.test(INTEGRATION));
    expect(result.current.tests[INTEGRATION.id]).toEqual({
      status: 'failed',
      error: 'Could not connect to crm: it timed out.',
    });
  });

  it('reports a refused save with the backend message', async () => {
    const { fetchMock, result } = await loaded(json([]));
    fetchMock.mockResolvedValueOnce(
      json({ error: 'validation_error', detail: 'mcp.local is not a public address.' }, 400),
    );

    const draft = { name: 'crm', url: 'https://mcp.local/mcp', headers: [] };
    await act(() => result.current.actions.create(draft));

    expect(result.current.notice).toEqual({
      kind: 'error',
      text: 'mcp.local is not a public address.',
    });
    expect(result.current.integrations).toEqual([]);
  });

  it('says when the list cannot be loaded', async () => {
    const { result } = await loaded(json({ error: 'server_error', detail: 'Down.' }, 500));
    expect(result.current.integrations).toBeNull();
    expect(result.current.notice).toEqual({ kind: 'error', text: 'Down.' });
  });
});
