import type { Schedule } from '../../core/api/types';

/** Shared by the schedule tests: a weekly schedule of a pipeline without named inputs. */
export const SCHEDULE: Schedule = {
  id: 4,
  pipeline_id: 3,
  pipeline_name: 'Competitor news',
  pipeline_inputs: [],
  frequency: 'weekly',
  time: '09:00',
  weekday: 0,
  day_of_month: null,
  timezone: 'Europe/Paris',
  input: 'Research my competitors’ news',
  inputs: {},
  enabled: true,
  next_run_at: '2026-10-26T08:00:00Z',
  last_run: null,
  last_error: null,
  created_at: '2026-10-24T10:00:00Z',
};

/** The same schedule for a pipeline that declares two named inputs. */
export const NAMED_SCHEDULE: Schedule = {
  ...SCHEDULE,
  id: 5,
  pipeline_name: 'Post writer',
  pipeline_inputs: [
    { name: 'topic', label: 'Topic', description: 'What to write about' },
    { name: 'audience', label: '', description: '' },
  ],
  input: '',
  inputs: { topic: 'bees', audience: 'kids' },
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** What a fetch stand-in sees of a call: its path, method and parsed body. */
export function callOf([path, init]: Parameters<typeof fetch>) {
  return {
    path: String(path),
    method: init?.method ?? 'GET',
    body: typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined,
  };
}
