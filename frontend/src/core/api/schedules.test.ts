import { afterEach, describe, expect, it, vi } from 'vitest';

import { API } from './endpoints';
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  previewSchedule,
  runScheduleNow,
  updateSchedule,
} from './schedules';

function ok(body: unknown = {}): Response {
  return new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });
}

const TIMING = {
  frequency: 'weekly',
  time: '09:00',
  weekday: 0,
  timezone: 'Europe/Paris',
} as const;

describe('schedules API', () => {
  afterEach(() => vi.restoreAllMocks());

  it('lists every schedule, or one pipeline’s', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async () => ok([]));

    await listSchedules();
    await listSchedules(3);

    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      API.schedules,
      `${API.schedules}?pipeline_id=3`,
    ]);
  });

  it('creates a schedule from its timing and what each run is given', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(ok({ id: 1 }));

    await createSchedule({ pipeline_id: 3, ...TIMING, input: 'go' });

    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe(API.schedules);
    expect(init?.method).toBe('POST');
    expect(JSON.parse(String(init?.body))).toEqual({ pipeline_id: 3, ...TIMING, input: 'go' });
  });

  it('changes, runs now, previews and deletes', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockImplementation(async (_path, init) =>
        init?.method === 'DELETE' ? new Response(null, { status: 204 }) : ok({ id: 7 }),
      );

    await updateSchedule(7, { enabled: false });
    await runScheduleNow(7);
    await previewSchedule(TIMING);
    await expect(deleteSchedule(7)).resolves.toBeUndefined();

    expect(fetchMock.mock.calls.map(([path, init]) => [path, init?.method ?? 'GET'])).toEqual([
      [API.schedule(7), 'PATCH'],
      [API.runSchedule(7), 'POST'],
      [API.previewSchedule, 'POST'],
      [API.schedule(7), 'DELETE'],
    ]);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({ enabled: false });
    expect(JSON.parse(String(fetchMock.mock.calls[2][1]?.body))).toEqual(TIMING);
  });

  it('surfaces a refused schedule as its error code and message', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: 'validation_error', detail: 'Unknown time zone.' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    await expect(createSchedule({ pipeline_id: 3, ...TIMING, input: 'go' })).rejects.toMatchObject({
      code: 'validation_error',
      message: 'Unknown time zone.',
    });
  });
});
