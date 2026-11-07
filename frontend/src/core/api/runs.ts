import { sharedRunPath } from '../routes';
import { API } from './endpoints';
import { request } from './client';
import type {
  PipelineRunRequest,
  Run,
  RunBudget,
  RunFeedback,
  RunPage,
  RunShare,
  RunStatus,
} from './types';

/** One page of the history, newest first, optionally of one pipeline or one status. */
export interface RunListQuery {
  limit: number;
  offset?: number;
  pipelineId?: number;
  status?: RunStatus;
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
  if (query.status !== undefined) params.set('status', query.status);
  return request<RunPage>(`${API.runs}?${params.toString()}`, { signal });
}

/** How many of your runs wait for you to approve or decline an action. */
export async function countWaitingRuns(signal?: AbortSignal): Promise<number> {
  return (await listRuns({ limit: 1, status: 'waiting' }, signal)).total;
}

export function getRun(runId: number, signal?: AbortSignal): Promise<Run> {
  return request<Run>(API.run(runId), { signal });
}

/** Stop a queued or running run; a finished one comes back unchanged. */
export function cancelRun(runId: number): Promise<Run> {
  return request<Run>(API.cancelRun(runId), { method: 'POST' });
}

/**
 * Continue a failed, stopped or interrupted run; any other comes back unchanged. A
 * `budget` sets new spending limits (a run that stopped at its limit needs a higher one).
 */
export function resumeRun(runId: number, budget?: RunBudget): Promise<Run> {
  return request<Run>(API.resumeRun(runId), { method: 'POST', body: budget });
}

/** Say whether an ended run was useful and leave a note (an active one is a 409 `conflict`). */
export function rateRun(runId: number, feedback: RunFeedback): Promise<Run> {
  return request<Run>(API.runFeedback(runId), { method: 'PUT', body: feedback });
}

/** The run's share link, or null while it is not shared. */
export function getRunShare(runId: number, signal?: AbortSignal): Promise<RunShare | null> {
  return request<RunShare | null>(API.runShare(runId), { signal });
}

/** Make the link (once the run has ended, else a 409); the same link comes back after that. */
export function shareRun(runId: number): Promise<RunShare> {
  return request<RunShare>(API.runShare(runId), { method: 'POST' });
}

/** Withdraw the link: it stops working at once. Nothing to withdraw is fine. */
export function unshareRun(runId: number): Promise<void> {
  return request<void>(API.runShare(runId), { method: 'DELETE' });
}

/** The report a link shows, read without an account; a withdrawn link is a 404. */
export function getSharedRun(token: string, signal?: AbortSignal): Promise<Run> {
  return request<Run>(API.sharedRun(token), { signal });
}

/** The page anyone with the link opens: this app's origin and the shared route. */
export function sharedRunUrl(token: string): string {
  return `${window.location.origin}${sharedRunPath(token)}`;
}

/** Only a finished run can be deleted (a running one is a 409 `conflict`). */
export function deleteRun(runId: number): Promise<void> {
  return request<void>(API.run(runId), { method: 'DELETE' });
}
