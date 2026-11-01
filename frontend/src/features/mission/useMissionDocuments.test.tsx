import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from '../../core/api/endpoints';
import { MAX_PLAN_DOCUMENTS } from '../../core/api/pipelines';
import type { ExtractedDocument } from '../../core/api/types';
import { deferred, hangUntilAborted, json } from './testData';
import { useMissionDocuments } from './useMissionDocuments';

const report: ExtractedDocument = {
  filename: 'report.pdf',
  format: 'pdf',
  text: 'Revenue grew.',
  characters: 13,
  pages: 2,
  truncated: false,
};

const page: ExtractedDocument = {
  filename: 'https://example.com/article',
  format: 'html',
  text: 'Page text.',
  characters: 10,
  pages: null,
  truncated: false,
};

const pdf = (name: string) => new File(['%PDF'], name, { type: 'application/pdf' });

/** The name of the file a request uploads. */
const uploaded = (init?: RequestInit) => ((init?.body as FormData).get('file') as File).name;

type Answer = (path: string, init?: RequestInit) => Response | Promise<Response>;

function serve(answer: Answer) {
  return vi
    .spyOn(globalThis, 'fetch')
    .mockImplementation(async (input, init) => answer(String(input), init));
}

describe('useMissionDocuments', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads each document on its own, as being read until it is', async () => {
    const slow = deferred<Response>();
    serve((_path, init) => (uploaded(init) === 'slow.pdf' ? slow.promise : json(report)));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addFiles([pdf('report.pdf'), pdf('slow.pdf')]));

    expect(result.current.items.map((item) => item.state)).toEqual(['reading', 'reading']);
    expect(result.current.status).toBe('Reading 2 documents…');
    await waitFor(() => expect(result.current.items[0].state).toBe('read'));
    expect(result.current.items[1].state).toBe('reading');
    expect(result.current.read).toEqual([report]);
    expect(result.current.status).toBe('report.pdf is ready: 2 pages · 13 characters.');

    slow.resolve(json({ ...report, filename: 'slow.pdf' }));
    await waitFor(() => expect(result.current.items[1].state).toBe('read'));
  });

  it('keeps the server’s reason when a document cannot be read', async () => {
    serve(() => json({ error: 'document_unreadable', detail: 'No text in this scan.' }, 422));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addFiles([pdf('scan.pdf')]));

    await waitFor(() => expect(result.current.items[0].state).toBe('failed'));
    expect(result.current.items[0]).toMatchObject({
      source: 'scan.pdf',
      error: 'No text in this scan.',
    });
    expect(result.current.read).toEqual([]);
  });

  it('reads a web page from its link', async () => {
    const fetchMock = serve(() => json(page));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addLink('https://example.com/a'));

    expect(result.current.items[0]).toMatchObject({
      kind: 'link',
      source: 'https://example.com/a',
    });
    await waitFor(() => expect(result.current.read).toEqual([page]));
    expect(fetchMock.mock.calls[0][0]).toBe(API.importDocumentUrl);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      url: 'https://example.com/a',
    });
  });

  it('cancels the reading of a document that is removed', async () => {
    let signal: AbortSignal | null | undefined;
    serve((_path, init) => {
      signal = init?.signal;
      return hangUntilAborted(init);
    });
    const { result } = renderHook(() => useMissionDocuments());
    act(() => result.current.addFiles([pdf('big.pdf')]));

    act(() => result.current.remove(result.current.items[0].id));

    expect(signal?.aborted).toBe(true);
    expect(result.current.items).toEqual([]);
    expect(result.current.status).toBe('big.pdf removed.');
  });

  it(`takes at most ${MAX_PLAN_DOCUMENTS}, and says so`, async () => {
    serve(() => json(report));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addFiles(['a', 'b', 'c', 'd', 'e', 'f', 'g'].map(pdf)));

    expect(result.current.items).toHaveLength(MAX_PLAN_DOCUMENTS);
    expect(result.current.full).toBe(true);
    expect(result.current.notice).toBe(
      'A mission takes up to 5 documents, so 2 were left out. Remove one to add another.',
    );

    act(() => result.current.addLink('https://example.com/a'));
    expect(result.current.items).toHaveLength(MAX_PLAN_DOCUMENTS);
    expect(result.current.notice).toContain('so 1 was left out');

    act(() => result.current.remove(result.current.items[0].id));
    expect(result.current.full).toBe(false);
    expect(result.current.notice).toBe('');
  });

  it('does not count one it could not read toward the limit', async () => {
    serve((_path, init) =>
      uploaded(init) === 'bad.pdf' ? json({ error: 'x', detail: 'Unreadable.' }, 422) : json(report),
    );
    const { result } = renderHook(() => useMissionDocuments());
    act(() => result.current.addFiles(['a', 'b', 'c', 'd', 'bad.pdf'].map(pdf)));
    await waitFor(() => expect(result.current.items[4].state).toBe('failed'));

    expect(result.current.full).toBe(false);
    expect(result.current.notice).toBe('');

    act(() => result.current.addLink('https://example.com/a'));

    expect(result.current.items).toHaveLength(MAX_PLAN_DOCUMENTS + 1);
    expect(result.current.full).toBe(true);
    expect(result.current.notice).toBe('That’s 5 documents, the most a mission takes.');
  });

  it('does not add a file or a page twice, and says it is already there', async () => {
    const fetchMock = serve((path) => (path === API.importDocumentUrl ? json(page) : json(report)));
    const { result } = renderHook(() => useMissionDocuments());
    const again = () => new File(['%PDF'], 'report.pdf', { lastModified: 1 });

    act(() => result.current.addFiles([again()]));
    act(() => result.current.addFiles([again()]));

    expect(result.current.items).toHaveLength(1);
    expect(result.current.notice).toBe('report.pdf is already attached.');

    act(() => result.current.addLink('https://example.com/a'));
    await waitFor(() => expect(result.current.read).toHaveLength(2));
    // The same page, by the link given or by where it led.
    act(() => result.current.addLink('https://EXAMPLE.com/a'));
    act(() => result.current.addLink(page.filename));

    expect(result.current.items).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(result.current.notice).toBe('example.com/article is already attached.');
  });

  it('takes another file that only shares the name', () => {
    serve((_path, init) => hangUntilAborted(init));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addFiles([new File(['%PDF'], 'report.pdf', { lastModified: 1 })]));
    act(() => result.current.addFiles([new File(['%PDF-2'], 'report.pdf', { lastModified: 2 })]));

    expect(result.current.items).toHaveLength(2);
    expect(result.current.notice).toBe('');
  });

  it('says the box is full once it is', () => {
    serve((_path, init) => hangUntilAborted(init));
    const { result } = renderHook(() => useMissionDocuments());

    act(() => result.current.addFiles(['a', 'b', 'c', 'd', 'e'].map(pdf)));

    expect(result.current.notice).toBe('That’s 5 documents, the most a mission takes.');
  });

  it('hands a document read while a run form is open straight to it', async () => {
    serve(() => json(report));
    const deliver = vi.fn(() => true);
    const { result } = renderHook(() => useMissionDocuments(deliver));

    act(() => result.current.addFiles([pdf('report.pdf')]));

    await waitFor(() => expect(deliver).toHaveBeenCalledWith(report));
    expect(result.current.items).toEqual([]);
    expect(result.current.status).toBe('report.pdf is in the run form.');
  });

  it('lets go of what a run form took, keeping what is still being read', async () => {
    const slow = deferred<Response>();
    serve((_path, init) => {
      const name = uploaded(init);
      if (name === 'slow.pdf') return slow.promise;
      return name === 'bad.pdf' ? json({ error: 'x', detail: 'Unreadable.' }, 422) : json(report);
    });
    const { result } = renderHook(() => useMissionDocuments());
    act(() => result.current.addFiles([pdf('report.pdf'), pdf('slow.pdf'), pdf('bad.pdf')]));
    await waitFor(() => expect(result.current.items[2].state).toBe('failed'));
    await waitFor(() => expect(result.current.items[0].state).toBe('read'));

    act(() => result.current.release(result.current.read));

    expect(result.current.items.map((item) => item.source)).toEqual(['slow.pdf']);
    expect(result.current.status).toBe('Your documents are in the run form.');
  });

  it('keeps a document read after the run form took the others', async () => {
    serve(() => json(report));
    const { result } = renderHook(() => useMissionDocuments());
    act(() => result.current.addFiles([pdf('report.pdf')]));
    await waitFor(() => expect(result.current.read).toHaveLength(1));

    act(() => result.current.release([]));

    expect(result.current.items).toHaveLength(1);
  });

  it('cancels every reading when the screen is left', () => {
    const signals: (AbortSignal | null | undefined)[] = [];
    serve((_path, init) => {
      signals.push(init?.signal);
      return hangUntilAborted(init);
    });
    const { result, unmount } = renderHook(() => useMissionDocuments());
    act(() => result.current.addFiles([pdf('a.pdf'), pdf('b.pdf')]));

    unmount();

    expect(signals).toHaveLength(2);
    expect(signals.every((signal) => signal?.aborted)).toBe(true);
  });
});
