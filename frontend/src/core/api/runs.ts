import { API } from './endpoints';
import { request } from './client';
import type { PipelineRunRequest, Run, RunPage } from './types';

/** One page of the history, newest first, optionally of one pipeline. */
export interface RunListQuery {
  limit: number;
  offset?: number;
  pipelineId?: number;
}

/** Queue a run of a saved pipeline; it executes on the server, so poll `getRun`. */
export function startRun(pipelineId: number, body: PipelineRunRequest): Promise<Run> {
  return request<Run>(API.pipelineRuns(pipelineId), { method: 'POST', body });
}

export function listRuns(query: RunListQuery, signal?: AbortSignal): Promise<RunPage> {
  const params = new URLSearchParams({
    limit: String(query.limit),
    offset: String(query.offset ?? 0),
  });
  if (query.pipelineId !== undefined) params.set('pipeline_id', String(query.pipelineId));
  return request<RunPage>(`${API.runs}?${params.toString()}`, { signal });
}

export function getRun(runId: number, signal?: AbortSignal): Promise<Run> {
  return request<Run>(API.run(runId), { signal });
}

/** Stop a queued or running run; a finished one comes back unchanged. */
export function cancelRun(runId: number): Promise<Run> {
  return request<Run>(API.cancelRun(runId), { method: 'POST' });
}

/** Continue a failed, stopped or interrupted run; any other comes back unchanged. */
export function resumeRun(runId: number): Promise<Run> {
  return request<Run>(API.resumeRun(runId), { method: 'POST' });
}

/** Only a finished run can be deleted (a running one is a 409 `conflict`). */
export function deleteRun(runId: number): Promise<void> {
  return request<void>(API.run(runId), { method: 'DELETE' });
}
