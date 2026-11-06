import { request } from './client';
import { API } from './endpoints';
import type { Memory } from './memoryTypes';

/** What the signed-in person told AIMIx to keep in mind. */
export function fetchMemory(signal?: AbortSignal): Promise<Memory> {
  return request<Memory>(API.memory, { signal });
}

/** Save the instructions; an empty text forgets them. */
export function saveMemory(instructions: string): Promise<Memory> {
  return request<Memory>(API.memory, { method: 'PUT', body: { instructions } });
}
