import { afterEach, describe, expect, it, vi } from 'vitest';

import { approveToolCall, declineToolCall } from './approvals';
import { API } from './endpoints';
import { countWaitingRuns, listRuns } from './runs';

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
}

describe('approvals API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('approves and declines a tool call of a run', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok({ id: 7 }));

    await approveToolCall(7, 31);
    await declineToolCall(7, 32);

    expect(fetchMock.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([
      ['/api/runs/7/approvals/31/approve', 'POST'],
      ['/api/runs/7/approvals/32/decline', 'POST'],
    ]);
    expect(API.approveToolCall(7, 31)).toBe('/api/runs/7/approvals/31/approve');
  });

  it('gives back the run, updated', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ id: 7, status: 'running' }));

    await expect(approveToolCall(7, 31)).resolves.toMatchObject({ id: 7, status: 'running' });
  });

  it('surfaces a clash or an expired request as its error code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ error: 'conflict', detail: 'This action was already declined.' }),
        { status: 409, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    await expect(approveToolCall(7, 31)).rejects.toMatchObject({
      code: 'conflict',
      status: 409,
      message: 'This action was already declined.',
    });
  });
});

describe('waiting runs', () => {
  afterEach(() => vi.restoreAllMocks());

  it('filters the history by status', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok());

    await listRuns({ limit: 5, pipelineId: 3, status: 'waiting' });

    expect(fetchMock.mock.calls[0][0]).toBe(
      `${API.runs}?limit=5&offset=0&pipeline_id=3&status=waiting`,
    );
  });

  it('counts the runs that wait for you with one small request', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(ok({ items: [{ id: 12 }], total: 3 }));

    await expect(countWaitingRuns()).resolves.toBe(3);

    expect(fetchMock.mock.calls[0][0]).toBe(`${API.runs}?limit=1&offset=0&status=waiting`);
  });
});
