import type { Integration, LLMSettings } from '../../core/api/types';

/** Shared by the Integrations tests: one server with a saved Authorization header. */
export const INTEGRATION: Integration = {
  id: 7,
  name: 'crm',
  url: 'https://mcp.crm.example/mcp',
  enabled: true,
  headers: [{ name: 'Authorization', hint: '1234' }],
  created_at: '2026-10-24T10:00:00Z',
};

/** Shared by the Settings tests: one provider with a saved key, one without. */
export const SETTINGS: LLMSettings = {
  provider: 'openrouter',
  providers: [
    {
      name: 'openrouter',
      key_source: 'saved',
      key_hint: '9876',
      default_model: 'vendor/fast',
      models: ['vendor/fast', 'vendor/smart'],
    },
    {
      name: 'togetherai',
      key_source: 'none',
      key_hint: '',
      default_model: 'other/big',
      models: ['other/big'],
    },
  ],
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A fetch stand-in for the whole page: each API path answers with its own body. */
export function byPath(bodies: Record<string, unknown>) {
  return async (input: RequestInfo | URL): Promise<Response> => {
    const path =
      typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url;
    return path in bodies
      ? json(bodies[path])
      : json({ error: 'not_found', detail: 'Not found.' }, 404);
  };
}
