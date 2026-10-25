import type { RunBudget, RunSummary } from '../../core/api/types';
import {
  formatCost,
  formatTokens,
  parseCost,
  parseTokenCount,
  totalTokens,
} from '../../core/usageFormat';

/** The error code of a run that stopped at its spending limit (api/exceptions.BudgetExceeded). */
export const BUDGET_ERROR_CODE = 'budget_exceeded';

/** A cost is a sum of many small floats: a run this close under its limit has reached it. */
const ROUNDING_SLACK = 1e-9;

/** The limits a run can have. */
export type LimitKind = 'cost' | 'tokens';

type Limited = Pick<RunSummary, 'max_cost_usd' | 'max_tokens' | 'usage'>;

/**
 * Which limit the run has reached, if any. The server stopped it there, and will
 * refuse to resume it under the same limit. Mirrors `limit_reached` in
 * backend/api/services/run_budget.py, which decides for real.
 */
export function limitReached(run: Limited): LimitKind | null {
  const { max_cost_usd: cost, max_tokens: tokens, usage } = run;
  if (cost !== null && usage.cost_usd !== null && usage.cost_usd + ROUNDING_SLACK >= cost) {
    return 'cost';
  }
  if (tokens !== null && totalTokens(usage) >= tokens) return 'tokens';
  return null;
}

/** The run's limits in words ("$0.50", "20,000 tokens"), none when it has no limit. */
export function limitParts(run: Pick<RunSummary, 'max_cost_usd' | 'max_tokens'>): string[] {
  const parts: string[] = [];
  if (run.max_cost_usd !== null) parts.push(formatCost(run.max_cost_usd));
  if (run.max_tokens !== null) parts.push(`${formatTokens(run.max_tokens)} tokens`);
  return parts;
}

/** What the run has used toward a limit, in words. */
export function usedText(run: Limited, kind: LimitKind): string {
  if (kind === 'cost') return formatCost(run.usage.cost_usd ?? 0);
  return `${formatTokens(totalTokens(run.usage))} tokens`;
}

/** A starting point for a higher limit: double the old one, as plain digits. */
export function suggestedLimit(run: Limited, kind: LimitKind): string {
  if (kind === 'tokens') return String((run.max_tokens ?? 0) * 2);
  const doubled = (run.max_cost_usd ?? 0) * 2;
  return doubled >= 0.1 ? doubled.toFixed(2) : String(Number(doubled.toFixed(4)));
}

/** The body of a resume for a new limit, or null when `text` is not a usable one. */
export function limitBudget(kind: LimitKind, text: string): RunBudget | null {
  if (kind === 'cost') {
    const cost = parseCost(text);
    return cost === null ? null : { max_cost_usd: cost };
  }
  const tokens = parseTokenCount(text);
  return tokens === null ? null : { max_tokens: tokens };
}

/** Why `text` cannot be the run's new limit, or null when it can. */
export function limitProblem(run: Limited, kind: LimitKind, text: string): string | null {
  const budget = limitBudget(kind, text);
  if (budget === null) {
    return kind === 'cost' ? 'Enter an amount above zero, like 1.00.' : 'Enter a whole number.';
  }
  const used = kind === 'cost' ? (run.usage.cost_usd ?? 0) : totalTokens(run.usage);
  const wanted = budget.max_cost_usd ?? budget.max_tokens ?? 0;
  if (wanted > used) return null;
  return `Enter more than ${usedText(run, kind)}, what this run has already used.`;
}
