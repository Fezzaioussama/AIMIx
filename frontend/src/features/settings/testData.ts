import type { Delivery } from '../../core/api/deliveryTypes';
import type { Integration, LLMSettings } from '../../core/api/types';
import type { Webhook } from '../../core/api/webhookTypes';

/** Shared by the Integrations tests: one server with a saved Authorization header. */
export const INTEGRATION: Integration = {
  id: 7,
  name: 'crm',
  url: 'https://mcp.crm.example/mcp',
  enabled: true,
  require_approval: true,
  headers: [{ name: 'Authorization', hint: '1234' }],
  created_at: '2026-10-24T10:00:00Z',
  oauth: '',
};

/** Shared by the Webhooks tests: a link another app called, which started a run. */
export const WEBHOOK: Webhook = {
  id: 7,
  pipeline_id: 3,
  pipeline_name: 'Weekly digest',
  enabled: true,
  last_called_at: '2026-10-30T08:00:00Z',
  last_error: null,
};

/** Shared by the Webhooks tests: a Slack address set by chat, still waiting for its OK. */
export const DELIVERY: Delivery = {
  id: 9,
  pipeline_id: 4,
  pipeline_name: 'Sales report',
  destination: 'hooks.slack.com',
  hint: 'XyZ9',
  service: 'Slack',
  confirmed: false,
  enabled: true,
  last_sent_at: null,
  last_error: null,
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
