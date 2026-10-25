import { API } from './endpoints';
import { request } from './client';
import type { Run } from './types';

/**
 * Let the tool call a run is waiting on act. The run comes back updated, so the
 * screen can show it going on at once. Sending the same answer twice is safe; the
 * other answer, or one for a request that expired, is a 409 `conflict`.
 */
export function approveToolCall(runId: number, approvalId: number): Promise<Run> {
  return request<Run>(API.approveToolCall(runId, approvalId), { method: 'POST' });
}

/** Refuse the tool call a run is waiting on; its agent is told and the run goes on. */
export function declineToolCall(runId: number, approvalId: number): Promise<Run> {
  return request<Run>(API.declineToolCall(runId, approvalId), { method: 'POST' });
}
