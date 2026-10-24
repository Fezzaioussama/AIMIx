import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import { cancelRun, deleteRun, getRun, listRuns, resumeRun, startRun } from './runs';

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
}

describe('runs API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts a run of a pipeline with its inputs', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ id: 1 }));

    await startRun(3, { inputs: { topic: 'bees' } });

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.pipelineRuns(3));
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('{"inputs":{"topic":"bees"}}');
  });

  it('pages the history and filters it by pipeline', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok());

    await listRuns({ limit: 20 });
    await listRuns({ limit: 5, offset: 10, pipelineId: 3 });

    expect(fetchMock.mock.calls[0][0]).toBe(`${API.runs}?limit=20&offset=0`);
    expect(fetchMock.mock.calls[1][0]).toBe(`${API.runs}?limit=5&offset=10&pipeline_id=3`);
  });

  it('reads, stops, resumes and deletes one run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (_path, init) =>
        init?.method === 'DELETE' ? new Response(null, { status: 204 }) : ok({ id: 7 }),
      );

    await getRun(7);
    await cancelRun(7);
    await resumeRun(7);
    await expect(deleteRun(7)).resolves.toBeUndefined();

    expect(fetchMock.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      [API.run(7), 'GET'],
      [API.cancelRun(7), 'POST'],
      [API.resumeRun(7), 'POST'],
      [API.run(7), 'DELETE'],
    ]);
  });

  it('surfaces a refused delete as its error code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'conflict', detail: 'Stop it first.' }), {
        status: 409,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(deleteRun(7)).rejects.toMatchObject({ code: 'conflict', status: 409 });
  });
});
