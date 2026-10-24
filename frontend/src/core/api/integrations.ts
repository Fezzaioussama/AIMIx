import { API } from './endpoints';
import { request } from './client';
import type {
  Integration,
  IntegrationInput,
  IntegrationPatch,
  IntegrationTestResult,
} from './types';

/**
 * A connection test reaches the server, then lists its tools, each bounded by the
 * backend's MCP_TIMEOUT_SECONDS (30 s by default); this leaves room for both.
 */
export const CONNECTION_TEST_TIMEOUT_MS = 60_000;

/** The account's own MCP servers, oldest first. */
export function listIntegrations(): Promise<Integration[]> {
  return request<Integration[]>(API.integrations);
}

export function createIntegration(input: IntegrationInput): Promise<Integration> {
  return request<Integration>(API.integrations, { method: 'POST', body: input });
}

export function updateIntegration(
  integrationId: number,
  patch: IntegrationPatch,
): Promise<Integration> {
  return request<Integration>(API.integration(integrationId), { method: 'PATCH', body: patch });
}

export function deleteIntegration(integrationId: number): Promise<void> {
  return request<void>(API.integration(integrationId), { method: 'DELETE' });
}

/** Connects to the server and lists the tools agents would get from it. */
export function testIntegration(
  integrationId: number,
  signal?: AbortSignal,
): Promise<IntegrationTestResult> {
  return request<IntegrationTestResult>(API.testIntegration(integrationId), {
    method: 'POST',
    timeoutMs: CONNECTION_TEST_TIMEOUT_MS,
    signal,
  });
}
