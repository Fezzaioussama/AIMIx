import { API } from './endpoints';
import { request } from './client';
import type { UsageReport } from './types';

/** What the signed-in account's runs started in the last `days` days used and cost. */
export function fetchUsage(days: number, signal?: AbortSignal): Promise<UsageReport> {
  return request<UsageReport>(`${API.usage}?days=${days}`, { signal });
}
