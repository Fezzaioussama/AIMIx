import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import {
  cancelRun,
  deleteRun,
  getRun,
  getRunShare,
  getSharedRun,
  listRuns,
  rateRun,
  resumeRun,
  shareRun,
  sharedRunUrl,
  startRun,
  unshareRun,
} from './runs';

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

  it('starts a run with a spending limit, which the server enforces', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ id: 1 }));

    await startRun(3, { input: 'seed', max_cost_usd: 0.5 });

    expect(fetchMock.mock.calls[0][1]?.body).toBe('{"input":"seed","max_cost_usd":0.5}');
  });

  it('resumes a run with new limits, or with none to keep its own', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok({ id: 7 }));

    await resumeRun(7);
    await resumeRun(7, { max_cost_usd: 2 });

    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toBe(API.resumeRun(7));
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{"max_cost_usd":2}');
  });

  it('rates a run and leaves a note for the next team', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ id: 7, rating: 1 }));

    await rateRun(7, { rating: 1, feedback: 'Shorter next time.' });

    const [path, init] = fetchMock.mock.calls[0];
    expect([path, init?.method]).toEqual([API.runFeedback(7), 'PUT']);
    expect(init?.body).toBe('{"rating":1,"feedback":"Shorter next time."}');
  });

  it('reads, makes and withdraws a run’s share link, and reads a shared run', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (_path, init) =>
        init?.method === 'DELETE' ? new Response(null, { status: 204 }) : ok({ token: 'tok' }),
      );

    await getRunShare(7);
    await shareRun(7);
    await unshareRun(7);
    await getSharedRun('tok/1');

    expect(fetchMock.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      [API.runShare(7), 'GET'],
      [API.runShare(7), 'POST'],
      [API.runShare(7), 'DELETE'],
      ['/api/shared/tok%2F1', 'GET'],
    ]);
    expect(sharedRunUrl('tok')).toBe(`${window.location.origin}/shared/tok`);
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
