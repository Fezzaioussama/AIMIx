import { API } from './endpoints';
import { request } from './client';
import type { ModelsResponse } from './types';

/** The backend owns the model catalogue; the client never hard-codes it (§3). */
export function fetchModels(): Promise<ModelsResponse> {
  return request<ModelsResponse>(API.models);
}
