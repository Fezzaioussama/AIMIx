import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../auth/tokenStorage';
import {
  DOCUMENT_ACCEPT,
  DOCUMENT_FORMATS,
  DOCUMENT_KINDS,
  extractDocument,
  importDocumentFromUrl,
} from './documents';
import { API } from './endpoints';
import type { ExtractedDocument } from './types';

describe('document formats', () => {
  it('accepts each extension once, in lower case with its dot', () => {
    const extensions = DOCUMENT_ACCEPT.split(',');
    expect(new Set(extensions).size).toBe(extensions.length);
    for (const extension of extensions) expect(extension).toMatch(/^\.[a-z]+$/);
    expect(extensions).toHaveLength(
      DOCUMENT_FORMATS.reduce((count, format) => count + format.extensions.length, 0),
    );
  });

  it('names the kinds as one list for copy', () => {
    expect(DOCUMENT_KINDS).toBe('PDF, Word, Excel, PowerPoint, image, HTML, CSV or text');
  });
});

const extracted: ExtractedDocument = {
  filename: 'notes.txt',
  format: 'txt',
  text: 'hello',
  characters: 5,
  pages: null,
  truncated: false,
};

describe('extractDocument', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('uploads the file as multipart form data with the session token', async () => {
    saveTokens({ access: 'token-abc' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(extracted), { status: 200 }));
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });

    const result = await extractDocument(file);

    expect(result).toEqual(extracted);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.extractDocument);
    expect(init?.method).toBe('POST');
    expect((init?.body as FormData).get('file')).toBe(file);
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token-abc');
  });

  it('surfaces the backend message when the file is refused', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          error: 'unsupported_document',
          detail: "'.exe' files are not supported.",
        }),
        { status: 415 },
      ),
    );

    await expect(extractDocument(new File(['x'], 'tool.exe'))).rejects.toMatchObject({
      code: 'unsupported_document',
      status: 415,
      message: "'.exe' files are not supported.",
    });
  });
});

describe('importDocumentFromUrl', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('has the server read the page at a link, with the session token', async () => {
    saveTokens({ access: 'token-abc' });
    const page = { ...extracted, filename: 'https://example.com/article', format: 'html' };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify(page), { status: 200 }));

    const result = await importDocumentFromUrl('https://example.com/a');

    expect(result).toEqual(page);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.importDocumentUrl);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ url: 'https://example.com/a' });
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token-abc');
  });

  it('surfaces why the page could not be opened', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: 'page_unreachable', detail: 'AIMIx couldn’t reach this site.' }),
        { status: 502 },
      ),
    );

    await expect(importDocumentFromUrl('https://nowhere.example')).rejects.toMatchObject({
      code: 'page_unreachable',
      status: 502,
      message: 'AIMIx couldn’t reach this site.',
    });
  });
});
