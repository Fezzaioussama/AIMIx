import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import { generatePipeline, listPipelines, savePipeline } from './pipelines';
import type { Pipeline } from './types';

const pipeline: Pipeline = { name: 'Drafts', steps: [] };

describe('savePipeline', () => {
  afterEach(() => vi.restoreAllMocks());

  it('creates a new pipeline and updates an existing one', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(
        async () =>
          new Response(JSON.stringify(pipeline), {
            headers: { 'Content-Type': 'application/json' },
          }),
      );

    await savePipeline(pipeline);
    await savePipeline({ ...pipeline, id: 7 });

    expect(fetchMock.mock.calls[0][0]).toBe(API.pipelines);
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST');
    expect(fetchMock.mock.calls[1][0]).toBe(API.pipeline(7));
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

describe('pipeline agent fields', () => {
  afterEach(() => vi.restoreAllMocks());

  it('defaults agent fields in older saved pipelines and generated plans', async () => {
    const legacy = {
      name: 'Legacy',
      steps: [{ order: 1, stage: 1, title: '', is_output: false, prompt: 'Work', model: 'v/m' }],
    };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(
        new Response(JSON.stringify([legacy]), { headers: { 'Content-Type': 'application/json' } }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ generated_pipeline: legacy, available_models: ['v/m'] }), {
          headers: { 'Content-Type': 'application/json' },
        }),
      );

    const saved = await listPipelines();
    const generated = await generatePipeline('Plan something', 'v/m');

    expect(saved[0].steps[0]).toMatchObject({ role: '', allowed_tools: null });
    expect(generated.generated_pipeline.steps[0]).toMatchObject({ role: '', allowed_tools: null });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
