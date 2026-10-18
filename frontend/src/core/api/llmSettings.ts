import { API } from './endpoints';
import { request } from './client';
import type { LLMSettings, LLMSettingsUpdate } from './types';

/** The signed-in account's provider, key status and default models. */
export function fetchLLMSettings(): Promise<LLMSettings> {
  return request<LLMSettings>(API.llmSettings);
}

export function saveLLMSettings(update: LLMSettingsUpdate): Promise<LLMSettings> {
  return request<LLMSettings>(API.llmSettings, { method: 'PUT', body: update });
}

/** Forget the saved key; the provider falls back to the server's, if any. */
export function removeProviderKey(provider: string): Promise<LLMSettings> {
  return request<LLMSettings>(API.llmSettingsKey(provider), { method: 'DELETE' });
}
