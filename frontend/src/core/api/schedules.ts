import { API } from './endpoints';
import { request } from './client';
import type {
  Run,
  Schedule,
  ScheduleInput,
  SchedulePatch,
  SchedulePreview,
  ScheduleTiming,
} from './types';

/** The account's schedules, oldest first; `pipelineId` narrows them to one pipeline's. */
export function listSchedules(pipelineId?: number, signal?: AbortSignal): Promise<Schedule[]> {
  const query = pipelineId === undefined ? '' : `?pipeline_id=${pipelineId}`;
  return request<Schedule[]>(`${API.schedules}${query}`, { signal });
}

export function createSchedule(body: ScheduleInput, signal?: AbortSignal): Promise<Schedule> {
  return request<Schedule>(API.schedules, { method: 'POST', body, signal });
}

export function updateSchedule(
  scheduleId: number,
  patch: SchedulePatch,
  signal?: AbortSignal,
): Promise<Schedule> {
  return request<Schedule>(API.schedule(scheduleId), { method: 'PATCH', body: patch, signal });
}

/** Its runs stay in the history. */
export function deleteSchedule(scheduleId: number, signal?: AbortSignal): Promise<void> {
  return request<void>(API.schedule(scheduleId), { method: 'DELETE', signal });
}

/** Start one of the schedule's runs now; it executes on the server, so poll `getRun`. */
export function runScheduleNow(scheduleId: number, signal?: AbortSignal): Promise<Run> {
  return request<Run>(API.runSchedule(scheduleId), { method: 'POST', signal });
}

/** When a schedule with this timing would first run. Nothing is saved. */
export function previewSchedule(
  timing: ScheduleTiming,
  signal?: AbortSignal,
): Promise<SchedulePreview> {
  return request<SchedulePreview>(API.previewSchedule, { method: 'POST', body: timing, signal });
}
