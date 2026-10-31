const LABELS: Record<string, string> = {
  openrouter: 'OpenRouter',
  togetherai: 'TogetherAI',
  meta: 'Meta',
};

/** Display name for a provider id; a provider without one shows its id. */
export function providerLabel(name: string): string {
  return LABELS[name] ?? name;
}
