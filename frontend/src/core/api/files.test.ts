import { afterEach, describe, expect, it, vi } from 'vitest';

import { clearTokens, saveTokens } from '../auth/tokenStorage';
import { API } from './endpoints';
import { deleteFile, downloadFile, listFiles, uploadFile } from './files';
import type { FileListing, WorkspaceFile } from './types';

const stored: WorkspaceFile = {
  path: 'notes.txt',
  size: 5,
  modified_at: '2026-10-24T10:00:00Z',
  type: 'txt',
};

const listing: FileListing = {
  files: [stored],
  used_bytes: 5,
  quota_bytes: 100_000_000,
  max_file_bytes: 10_000_000,
  allowed_extensions: ['.pdf', '.txt'],
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('files api', () => {
  afterEach(() => {
    clearTokens();
    vi.restoreAllMocks();
  });

  it('lists the files with the session token', async () => {
    saveTokens({ access: 'token-abc' });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(json(listing));

    await expect(listFiles()).resolves.toEqual(listing);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.files);
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token-abc');
  });

  it('uploads one file as multipart, asking to replace only when told to', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(() => Promise.resolve(json([stored], 201)));
    const file = new File(['hello'], 'notes.txt', { type: 'text/plain' });

    await expect(uploadFile(file)).resolves.toEqual(stored);
    await uploadFile(file, { replace: true });

    const [first, second] = fetchMock.mock.calls.map(([, init]) => init?.body as FormData);
    expect(fetchMock.mock.calls[0][0]).toBe(API.files);
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
    expect(first.get('files')).toBe(file);
    expect(first.has('replace')).toBe(false);
    expect(second.get('replace')).toBe('true');
  });

  it('downloads with the session header, never with a token in the address', async () => {
    saveTokens({ access: 'token-abc' });
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('# Report', { status: 200 }));

    const content = await downloadFile('reports/Q3 report #1.md');

    expect(content.size).toBe('# Report'.length);
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe('/api/files/reports/Q3%20report%20%231.md');
    expect(String(path)).not.toContain('token');
    expect((init?.headers as Headers).get('Authorization')).toBe('Bearer token-abc');
  });

  it('deletes by path and surfaces a refusal with its code', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(
        json({ error: 'not_found', detail: "'notes.txt' does not exist in the workspace." }, 404),
      );

    await expect(deleteFile('notes.txt')).resolves.toBeUndefined();
    await expect(deleteFile('notes.txt')).rejects.toMatchObject({
      code: 'not_found',
      status: 404,
    });
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
    expect(fetchMock.mock.calls[0][0]).toBe(API.file('notes.txt'));
  });
});
