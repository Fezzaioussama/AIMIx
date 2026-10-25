import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import { fetchUsage } from './usage';

describe('usage API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('asks for the usage of the last days and passes the abort signal on', async () => {
    const report = { days: 30, since: '2026-09-25T00:00:00Z', runs: 0, pipelines: [] };
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        new Response(JSON.stringify(report), { headers: { 'Content-Type': 'application/json' } }),
      );
    const controller = new AbortController();

    await expect(fetchUsage(30, controller.signal)).resolves.toEqual(report);

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(`${API.usage}?days=30`);
    expect(init?.method).toBe('GET');
    expect(init?.signal).toBeInstanceOf(AbortSignal);
  });

  it('surfaces a refused period as its error code', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'validation_error', detail: 'Bad days.' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(fetchUsage(0)).rejects.toMatchObject({ code: 'validation_error', status: 400 });
  });
});
