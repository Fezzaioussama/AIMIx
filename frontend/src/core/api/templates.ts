import { API } from './endpoints';
import { request } from './client';
import type { MissionTemplate, Pipeline } from './types';

export function listTemplates(signal?: AbortSignal): Promise<MissionTemplate[]> {
  return request<MissionTemplate[]>(API.templates, { signal });
}

/**
 * Creates the signed-in user's own pipeline from a template, named after it.
 * The server gives every step the user's default model and only the tools they have.
 */
export function createFromTemplate(slug: string, signal?: AbortSignal): Promise<Pipeline> {
  return request<Pipeline>(API.createFromTemplate(slug), { method: 'POST', body: {}, signal });
}
