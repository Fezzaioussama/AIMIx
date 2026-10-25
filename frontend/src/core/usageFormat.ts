/** Tokens and costs as screens word them (shared like `time.ts`). */
import type { RunStep, Usage } from './api/types';

/** What the screen says for a cost nobody can know (a model without a published price). */
export const UNKNOWN_COST = 'Cost unknown for this model';

const NUMBER = new Intl.NumberFormat('en-US');
const MONEY = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * "$0.0123" under ten cents, else "$0.52" or "$1,234.50"; "<$0.0001" for dust. Mirrors
 * `format_usd` in backend/api/services/run_budget.py, which words the server's messages.
 */
export function formatCost(usd: number): string {
  if (usd === 0) return '$0.00';
  if (usd < 0.0001) return '<$0.0001';
  return usd < 0.1 ? `$${usd.toFixed(4)}` : `$${MONEY.format(usd)}`;
}

/** "1,234": any whole count, of tokens or of runs. */
export function formatCount(count: number): string {
  return NUMBER.format(count);
}

export function formatTokens(count: number): string {
  return formatCount(count);
}

/** A dollar amount a person typed: "0.5", "$0.50", "1,000"; null unless it is above zero. */
export function parseCost(text: string): number | null {
  const typed = text.trim().replace(/^\$/, '').replace(/,/g, '').trim();
  if (!/^(\d+\.?\d*|\.\d+)$/.test(typed)) return null;
  const value = Number(typed);
  return Number.isFinite(value) && value > 0 ? value : null;
}

/** A number of tokens a person typed: "20000" or "20,000"; null unless it is a whole number above zero. */
export function parseTokenCount(text: string): number | null {
  const typed = text.trim().replace(/[,\s]/g, '');
  if (!/^\d+$/.test(typed)) return null;
  const value = Number(typed);
  return Number.isSafeInteger(value) && value > 0 ? value : null;
}

export function totalTokens(usage: Pick<Usage, 'input_tokens' | 'output_tokens'>): number {
  return usage.input_tokens + usage.output_tokens;
}

/** "1,234 tokens in, 567 out". */
export function tokenBreakdown(usage: Pick<Usage, 'input_tokens' | 'output_tokens'>): string {
  return `${formatTokens(usage.input_tokens)} tokens in, ${formatTokens(usage.output_tokens)} out`;
}

/** A step's usage in the shape of a run's: it is complete unless tokens went unpriced. */
export function usageOfStep(
  step: Pick<RunStep, 'input_tokens' | 'output_tokens' | 'cost_usd'>,
): Usage {
  const unpriced = step.cost_usd === null && totalTokens(step) > 0;
  return {
    input_tokens: step.input_tokens,
    output_tokens: step.output_tokens,
    cost_usd: step.cost_usd,
    cost_complete: !unpriced,
  };
}

/** How one usage reads on screen. */
export interface CostView {
  /** The full words: "$0.0123", "$0.0123 or more", or "Cost unknown for this model". */
  text: string;
  /** For tight rows: "$0.0123", "$0.0123+" or "Cost unknown". */
  short: string;
  /** What a hover reveals: the token counts, and why a cost is only a floor. */
  tip: string;
  /** Every call was priced, so `text` is the whole cost. */
  exact: boolean;
}

/** The words for a usage; null while nothing was used, so there is nothing to say. */
export function describeCost(usage: Usage): CostView | null {
  const tokens = tokenBreakdown(usage);
  if (usage.cost_usd === null) {
    if (totalTokens(usage) === 0) return null;
    return { text: UNKNOWN_COST, short: 'Cost unknown', tip: tokens, exact: false };
  }
  const cost = formatCost(usage.cost_usd);
  if (!usage.cost_complete) {
    const why = 'Some of it ran on a model whose cost is unknown, so the real cost is higher.';
    return { text: `${cost} or more`, short: `${cost}+`, tip: `${tokens}. ${why}`, exact: false };
  }
  return { text: cost, short: cost, tip: tokens, exact: true };
}
