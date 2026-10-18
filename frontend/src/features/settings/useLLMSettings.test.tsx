import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { SETTINGS, json } from './testData';
import { toUpdate, useLLMSettings } from './useLLMSettings';

describe('toUpdate', () => {
  it('sends only typed keys and changed models', () => {
    const drafts = {
      openrouter: { apiKey: '', model: 'vendor/fast' },
      togetherai: { apiKey: '  tg-key  ', model: 'other/big' },
    };
    expect(toUpdate(SETTINGS, 'togetherai', drafts)).toEqual({
      provider: 'togetherai',
      providers: [{ name: 'togetherai', default_model: 'other/big', api_key: 'tg-key' }],
    });
  });
});

describe('useLLMSettings', () => {
  afterEach(() => vi.restoreAllMocks());

  it('saves the form and forgets the typed key once it is stored', async () => {
    const saved = {
      ...SETTINGS,
      providers: [{ ...SETTINGS.providers[0], key_hint: '4321', default_model: 'vendor/smart' }],
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(SETTINGS))
      .mockResolvedValueOnce(json(saved));
    const { result } = renderHook(() => useLLMSettings());
    await waitFor(() => expect(result.current.settings).toEqual(SETTINGS));
    expect(result.current.dirty).toBe(false);

    act(() => result.current.actions.editDraft('openrouter', { apiKey: 'sk-new-4321' }));
    act(() => result.current.actions.editDraft('openrouter', { model: 'vendor/smart' }));
    expect(result.current.dirty).toBe(true);
    await act(() => result.current.actions.save());

    const [path, init] = fetchMock.mock.calls[1];
    expect(path).toBe(API.llmSettings);
    expect(init?.method).toBe('PUT');
    expect(JSON.parse(String(init?.body))).toEqual({
      provider: 'openrouter',
      providers: [{ name: 'openrouter', default_model: 'vendor/smart', api_key: 'sk-new-4321' }],
    });
    expect(result.current.drafts.openrouter).toEqual({ apiKey: '', model: 'vendor/smart' });
    expect(result.current.notice).toEqual({ kind: 'success', text: 'Settings saved.' });
  });

  it('removes a saved key without discarding other edits', async () => {
    const removed = {
      ...SETTINGS,
      providers: [
        { ...SETTINGS.providers[0], key_source: 'none', key_hint: '' },
        SETTINGS.providers[1],
      ],
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(SETTINGS))
      .mockResolvedValueOnce(json(removed));
    const { result } = renderHook(() => useLLMSettings());
    await waitFor(() => expect(result.current.settings).not.toBeNull());

    act(() => result.current.actions.chooseProvider('togetherai'));
    await act(() => result.current.actions.removeKey('openrouter'));

    expect(fetchMock.mock.calls[1][0]).toBe(API.llmSettingsKey('openrouter'));
    expect(fetchMock.mock.calls[1][1]?.method).toBe('DELETE');
    expect(result.current.settings?.providers[0].key_source).toBe('none');
    expect(result.current.provider).toBe('togetherai');
  });

  it('reports a failed save with the backend message', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(json(SETTINGS))
      .mockResolvedValueOnce(json({ error: 'validation_error', detail: 'Unknown model.' }, 400));
    const { result } = renderHook(() => useLLMSettings());
    await waitFor(() => expect(result.current.settings).not.toBeNull());

    act(() => result.current.actions.chooseProvider('togetherai'));
    await act(() => result.current.actions.save());

    expect(result.current.notice).toEqual({ kind: 'error', text: 'Unknown model.' });
    expect(result.current.status).toBe('idle');
  });
});
