import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { json } from '../settings/testData';
import { TEMPLATES } from './testData';
import { useTemplates } from './useTemplates';

const CREATED = { id: 42, name: 'Document digest', inputs: [], steps: [] };

describe('useTemplates', () => {
  afterEach(() => vi.restoreAllMocks());

  it('loads the gallery', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(TEMPLATES));

    const { result } = renderHook(() => useTemplates());

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.templates).toEqual(TEMPLATES);
    expect(fetchMock.mock.calls[0][0]).toBe(API.templates);
  });

  it('reports a failed load and loads again on request', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json({ error: 'server_error', detail: 'Something broke.' }, 500))
      .mockResolvedValueOnce(json(TEMPLATES));
    const { result } = renderHook(() => useTemplates());
    await waitFor(() => expect(result.current.status).toBe('failed'));
    expect(result.current.loadError).toBe('Something broke.');

    act(() => result.current.actions.reload());

    await waitFor(() => expect(result.current.status).toBe('ready'));
    expect(result.current.templates).toHaveLength(3);
  });

  it('creates the pipeline from the chosen template', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(TEMPLATES))
      .mockResolvedValueOnce(json(CREATED, 201));
    const { result } = renderHook(() => useTemplates());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    const created = await act(() => result.current.actions.create(TEMPLATES[2]));

    expect(created?.id).toBe(42);
    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe(API.createFromTemplate('document-digest'));
    expect(init?.method).toBe('POST');
    expect(result.current.creating).toBeNull();
  });

  it('says which template could not be used and frees the gallery again', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(TEMPLATES))
      .mockResolvedValueOnce(json({ error: 'not_found', detail: 'Template was not found.' }, 404));
    const { result } = renderHook(() => useTemplates());
    await waitFor(() => expect(result.current.status).toBe('ready'));

    const created = await act(() => result.current.actions.create(TEMPLATES[0]));

    expect(created).toBeNull();
    expect(result.current.createError).toBe(
      'Could not start "Market research brief". Template was not found.',
    );
    expect(result.current.creating).toBeNull();
  });
});
