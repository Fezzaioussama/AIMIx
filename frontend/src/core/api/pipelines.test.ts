import { afterEach, describe, expect, it, vi } from 'vitest';

import { savePipeline } from './pipelines';
import type { Pipeline } from './types';

const pipeline: Pipeline = { name: 'Drafts', steps: [] };

describe('savePipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('creates a new pipeline and updates an existing one', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      new Response(JSON.stringify(pipeline), { headers: { 'Content-Type': 'application/json' } }),
    );

    await savePipeline(pipeline);
    await savePipeline({ ...pipeline, id: 7 });

    expect(fetchMock.mock.calls[0][0]).toBe('/api/pipelines/');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
    expect(fetchMock.mock.calls[1][0]).toBe('/api/pipelines/7/');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('PUT');
  });

  it('surfaces an update failure from the API', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'not_found', detail: 'Pipeline missing' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(savePipeline({ ...pipeline, id: 7 })).rejects.toMatchObject({
      code: 'not_found',
      message: 'Pipeline missing',
    });
  });
});
