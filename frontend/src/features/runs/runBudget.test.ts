import { describe, expect, it } from 'vitest';

import {
  limitBudget,
  limitParts,
  limitProblem,
  limitReached,
  suggestedLimit,
  usedText,
} from './runBudget';
import { usageOf } from './testData';

const run = (
  limits: { max_cost_usd?: number | null; max_tokens?: number | null },
  usage = usageOf(1000, 500, 0.52),
) => ({ max_cost_usd: null, max_tokens: null, usage, ...limits });

describe('limitReached', () => {
  it('is reached at the cost limit, and not before', () => {
    expect(limitReached(run({ max_cost_usd: 0.5 }))).toBe('cost');
    expect(limitReached(run({ max_cost_usd: 0.52 }))).toBe('cost');
    expect(limitReached(run({ max_cost_usd: 0.53 }))).toBeNull();
  });

  it('counts a sum a hair under the limit as reached', () => {
    // Ten $0.01 calls add up to 0.09999999999999999 in floating point.
    expect(limitReached(run({ max_cost_usd: 0.1 }, usageOf(1, 1, 0.09999999999999999)))).toBe(
      'cost',
    );
  });

  it('is reached at the token limit, counting tokens in and out', () => {
    expect(limitReached(run({ max_tokens: 1500 }))).toBe('tokens');
    expect(limitReached(run({ max_tokens: 1501 }))).toBeNull();
  });

  it('names the cost limit when both are reached', () => {
    expect(limitReached(run({ max_cost_usd: 0.1, max_tokens: 10 }))).toBe('cost');
  });

  it('never reaches a limit it does not have, or a cost limit on an unknown cost', () => {
    expect(limitReached(run({}))).toBeNull();
    expect(limitReached(run({ max_cost_usd: 0.01 }, usageOf(1000, 500, null)))).toBeNull();
    expect(
      limitReached(run({ max_cost_usd: 0.01, max_tokens: 100 }, usageOf(1000, 500, null))),
    ).toBe('tokens');
  });
});

describe('limit words', () => {
  it('lists the limits a run has', () => {
    expect(limitParts({ max_cost_usd: 0.5, max_tokens: null })).toEqual(['$0.50']);
    expect(limitParts({ max_cost_usd: 0.5, max_tokens: 20000 })).toEqual([
      '$0.50',
      '20,000 tokens',
    ]);
    expect(limitParts({ max_cost_usd: null, max_tokens: null })).toEqual([]);
  });

  it('says what has been used toward each kind of limit', () => {
    expect(usedText(run({}), 'cost')).toBe('$0.52');
    expect(usedText(run({}), 'tokens')).toBe('1,500 tokens');
    expect(usedText(run({}, usageOf(10, 5, null)), 'cost')).toBe('$0.00');
  });
});

describe('a higher limit', () => {
  it('starts from double what the run used, or its old limit if that is more', () => {
    // Stopped at its $0.50 limit having used $0.52: double the $0.52.
    expect(suggestedLimit(run({ max_cost_usd: 0.5 }), 'cost')).toBe('1.04');
    // Used less than the limit it has: double the limit.
    expect(suggestedLimit(run({ max_cost_usd: 0.5 }, usageOf(10, 5, 0.1)), 'cost')).toBe('1.00');
    expect(suggestedLimit(run({ max_tokens: 20000 }), 'tokens')).toBe('40000');
    expect(suggestedLimit(run({ max_tokens: 1000 }), 'tokens')).toBe('3000');
  });

  it('writes a small cost with the four decimals the screen shows, rounded up', () => {
    // 0.0022 doubled is exactly 0.0044, not rounded up to 0.0045 by float noise.
    expect(suggestedLimit(run({ max_cost_usd: 0.001 }, usageOf(1, 1, 0.0022)), 'cost')).toBe(
      '0.0044',
    );
    // The real figure behind "$0.0022": a call of 51 tokens in and 40 out.
    expect(suggestedLimit(run({ max_cost_usd: 0.001 }, usageOf(1, 1, 0.002211)), 'cost')).toBe(
      '0.0045',
    );
    // Dust never turns into "0", or into an exponent.
    expect(suggestedLimit(run({ max_cost_usd: 0.00001 }, usageOf(1, 1, 0.00003)), 'cost')).toBe(
      '0.0001',
    );
    expect(suggestedLimit(run({ max_cost_usd: 1e-7 }, usageOf(1, 1, 1e-7)), 'cost')).toBe('0.0001');
  });

  it('is always a limit the form accepts, whatever was used', () => {
    for (const used of [0.00003, 0.0022, 0.0499, 0.05, 0.52, 3.333, 1234.5]) {
      const stopped = run({ max_cost_usd: used / 2 }, usageOf(100, 50, used));
      const suggestion = suggestedLimit(stopped, 'cost');

      expect(Number(suggestion)).toBeGreaterThan(used);
      expect(limitProblem(stopped, 'cost', suggestion)).toBeNull();
    }
  });

  it('turns what was typed into the resume body, or nothing', () => {
    expect(limitBudget('cost', '$1.50')).toEqual({ max_cost_usd: 1.5 });
    expect(limitBudget('tokens', '40,000')).toEqual({ max_tokens: 40000 });
    expect(limitBudget('cost', 'a lot')).toBeNull();
    expect(limitBudget('tokens', '1.5')).toBeNull();
  });

  it('must be more than the run has already used', () => {
    const stopped = run({ max_cost_usd: 0.5 });

    expect(limitProblem(stopped, 'cost', '1.00')).toBeNull();
    expect(limitProblem(stopped, 'cost', '0.52')).toBe(
      'Enter more than $0.52, what this run has already used.',
    );
    expect(limitProblem(stopped, 'cost', '0.10')).toContain('Enter more than $0.52');
    expect(limitProblem(stopped, 'cost', 'x')).toBe('Enter an amount above zero, like 1.00.');
    expect(limitProblem(run({ max_tokens: 1000 }), 'tokens', '1500')).toContain(
      'Enter more than 1,500 tokens',
    );
    expect(limitProblem(run({ max_tokens: 1000 }), 'tokens', 'x')).toBe('Enter a whole number.');
  });
});
