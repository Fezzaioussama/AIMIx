import type { LLMSettings } from '../../core/api/types';

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
