import { vi } from 'vitest';

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

/** What a fetch stand-in saw of a call: its path (with any query), method and parsed body. */
export interface Call {
  path: string;
  method: string;
  body: unknown;
}

export function callOf([path, init]: Parameters<typeof fetch>): Call {
  return {
    path: String(path),
    method: init?.method ?? 'GET',
    body: typeof init?.body === 'string' ? (JSON.parse(init.body) as unknown) : undefined,
  };
}

/**
 * What answers a call: a body, a ready `Response`, or a function of the call making either
 * (or a promise of either, to hold a request open).
 */
type Answer = unknown;

/**
 * A fetch stand-in answering each "METHOD /path" from `table` (the query is ignored when no
 * entry names it). Anything else is a 404. Returns the calls it saw, in order.
 */
export function serve(table: Record<string, Answer>): Call[] {
  const calls: Call[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const call = callOf([input, init]);
    calls.push(call);
    const answer =
      table[`${call.method} ${call.path}`] ?? table[`${call.method} ${call.path.split('?')[0]}`];
    if (answer === undefined) return json({ error: 'not_found', detail: 'Not found.' }, 404);
    const value = await (typeof answer === 'function'
      ? (answer as (call: Call) => unknown)(call)
      : answer);
    return value instanceof Response ? value : json(value);
  });
  return calls;
}

/** A refusal in the API's error shape. */
export function refusal(detail: string, status = 400, error = 'validation_error'): Response {
  return json({ error, detail }, status);
}
