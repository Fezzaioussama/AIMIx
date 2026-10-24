import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../auth/tokenStorage';
import { extractDocument } from './documents';
import { API } from './endpoints';
import type { ExtractedDocument } from './types';

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
    saveTokens({ access: 'token-abc', refresh: 'refresh-abc' });
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
