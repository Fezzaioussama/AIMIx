import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import type { Pipeline } from '../../core/api/types';
import { draft, json, pendingFetch, revision } from './revisionTestData';
import { useRevisePipeline } from './useRevisePipeline';

function renderRevise(pipeline: Pipeline = draft) {
  return renderHook((props: { pipeline: Pipeline }) => useRevisePipeline(props.pipeline), {
    initialProps: { pipeline },
  });
}

describe('useRevisePipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('proposes a revision of the draft that keeps its id', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { result } = renderRevise();

    await act(async () => result.current.propose('  Add an SEO agent  '));

    expect(result.current.proposal?.pipeline.id).toBe(7);
    expect(result.current.proposal?.pipeline.steps).toHaveLength(3);
    expect(result.current.proposal?.changes).toEqual(revision.changes);
    expect(result.current.busy).toBe(false);
    expect(fetchMock.mock.calls[0][0]).toBe(API.revisePipeline);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.instruction).toBe('Add an SEO agent');
    expect(body.pipeline.name).toBe('Launch kit');
    expect(body).not.toHaveProperty('planner_model');
  });

  it('sends the chosen planner model', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { result } = renderRevise();

    await act(async () => result.current.propose('Add an SEO agent', 'vendor/planner'));

    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body)).planner_model).toBe(
      'vendor/planner',
    );
  });

  it('asks for an instruction before calling the server', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const { result } = renderRevise();

    await act(async () => result.current.propose('   '));

    expect(result.current.error).toBe('Describe the change you want first.');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('words an unusable planner answer plainly and keeps other reasons', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        json({ error: 'upstream_response_invalid', detail: 'Invalid JSON: line 1' }, 502),
      )
      .mockResolvedValueOnce(
        json({ error: 'provider_not_configured', detail: 'No API key is set.' }, 503),
      );
    const { result } = renderRevise();

    await act(async () => result.current.propose('Add an SEO agent'));
    expect(result.current.error).toBe(
      'AIMIx could not turn that into a change. Try saying it another way.',
    );
    expect(result.current.proposal).toBeNull();

    await act(async () => result.current.propose('Add an SEO agent'));
    expect(result.current.error).toBe('No API key is set.');
  });

  it('sets a proposal aside once the draft is edited', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(revision));
    const { result, rerender } = renderRevise();
    await act(async () => result.current.propose('Add an SEO agent'));

    rerender({ pipeline: { ...draft, name: 'Edited by hand' } });

    expect(result.current.proposal).toBeNull();
    expect(result.current.stale).toBe(true);
    act(() => result.current.discard());
    expect(result.current.stale).toBe(false);
  });

  it('drops an answer for a draft that changed while it was being made', async () => {
    let answer: (response: Response) => void = () => {};
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      new Promise<Response>((resolve) => {
        answer = resolve;
      }),
    );
    const { result, rerender } = renderRevise();
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.propose('Add an SEO agent');
    });

    rerender({ pipeline: { ...draft, name: 'Edited by hand' } });
    await act(async () => {
      answer(json(revision));
      await pending;
    });

    expect(result.current.proposal).toBeNull();
    expect(result.current.stale).toBe(false);
    expect(result.current.error).toMatch(/changed while AIMIx was working/);
  });

  it('stops waiting when cancelled, without an error', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(pendingFetch);
    const { result } = renderRevise();
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.propose('Add an SEO agent');
    });
    expect(result.current.busy).toBe(true);

    await act(async () => {
      result.current.cancel();
      await pending;
    });

    expect(result.current.busy).toBe(false);
    expect(result.current.error).toBe('');
    expect(result.current.proposal).toBeNull();
  });

  it('cancels the request when the screen is left', () => {
    let signal: AbortSignal | null | undefined;
    vi.spyOn(globalThis, 'fetch').mockImplementation((path, init) => {
      signal = init?.signal;
      return pendingFetch(path, init);
    });
    const { result, unmount } = renderRevise();
    act(() => {
      void result.current.propose('Add an SEO agent');
    });

    unmount();

    expect(signal?.aborted).toBe(true);
  });
});
