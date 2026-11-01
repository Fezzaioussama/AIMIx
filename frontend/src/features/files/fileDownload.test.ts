import { afterEach, describe, expect, it, vi } from 'vitest';

import { downloadFile } from '../../core/api/files';
import { saveBlob } from '../../core/saveBlob';
import { downloadAndSave } from './fileDownload';

vi.mock('../../core/api/files', () => ({ downloadFile: vi.fn() }));
vi.mock('../../core/saveBlob', () => ({ saveBlob: vi.fn() }));

describe('downloadAndSave', () => {
  afterEach(() => vi.clearAllMocks());

  it('fetches the file with the session and saves it under its own name', async () => {
    const content = new Blob(['%PDF-1.4']);
    vi.mocked(downloadFile).mockResolvedValue(content);
    const { signal } = new AbortController();

    await downloadAndSave('reports/q3.pdf', signal);

    expect(downloadFile).toHaveBeenCalledWith('reports/q3.pdf', signal);
    expect(saveBlob).toHaveBeenCalledWith(content, 'q3.pdf');
  });

  it('saves nothing once the screen is gone', async () => {
    const controller = new AbortController();
    vi.mocked(downloadFile).mockImplementation(async () => {
      controller.abort();
      return new Blob(['late']);
    });

    await downloadAndSave('notes.txt', controller.signal);

    expect(saveBlob).not.toHaveBeenCalled();
  });

  it('lets a failed download reach the caller', async () => {
    vi.mocked(downloadFile).mockRejectedValue(new Error('offline'));

    await expect(downloadAndSave('notes.txt', new AbortController().signal)).rejects.toThrow(
      'offline',
    );
    expect(saveBlob).not.toHaveBeenCalled();
  });
});
