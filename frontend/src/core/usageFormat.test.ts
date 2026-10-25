import { describe, expect, it } from 'vitest';

import type { Usage } from './api/types';
import {
  UNKNOWN_COST,
  describeCost,
  formatCost,
  formatCount,
  formatTokens,
  parseCost,
  parseTokenCount,
  tokenBreakdown,
  totalTokens,
  usageOfStep,
} from './usageFormat';

const usage = (overrides: Partial<Usage> = {}): Usage => ({
  input_tokens: 1234,
  output_tokens: 567,
  cost_usd: 0.0123,
  cost_complete: true,
  ...overrides,
});

describe('formatCost', () => {
  // The same cases as format_usd in backend/tests/test_run_budget.py: the screen and
  // the server's messages word an amount alike.
  it.each([
    [0, '$0.00'],
    [0.00001, '<$0.0001'],
    [0.0001, '$0.0001'],
    [0.0123, '$0.0123'],
    [0.0999, '$0.0999'],
    [0.1, '$0.10'],
    [0.52, '$0.52'],
    [12, '$12.00'],
    [1234.5, '$1,234.50'],
  ])('writes %s as %s', (value, text) => {
    expect(formatCost(value)).toBe(text);
  });
});

describe('counts', () => {
  it('groups digits', () => {
    expect(formatTokens(1234567)).toBe('1,234,567');
    expect(formatCount(7)).toBe('7');
    expect(totalTokens(usage())).toBe(1801);
  });

  it('says what went in and what came out', () => {
    expect(tokenBreakdown(usage())).toBe('1,234 tokens in, 567 out');
  });
});

describe('parseCost', () => {
  it.each([
    ['0.5', 0.5],
    ['$0.50', 0.5],
    [' 1,000 ', 1000],
    ['.25', 0.25],
    ['5.', 5],
    ['$ 2', 2],
  ])('reads %j as %s', (typed, value) => {
    expect(parseCost(typed)).toBe(value);
  });

  it.each([
    '',
    '  ',
    '0',
    '0.00',
    '-1',
    'abc',
    '1e3',
    '1.2.3',
    '$',
    'NaN',
    'Infinity',
    '5 dollars',
  ])('refuses %j', (typed) => {
    expect(parseCost(typed)).toBeNull();
  });
});

describe('parseTokenCount', () => {
  it('reads whole numbers above zero, with or without separators', () => {
    expect(parseTokenCount('20000')).toBe(20000);
    expect(parseTokenCount(' 20,000 ')).toBe(20000);
  });

  it.each(['', '0', '-5', '1.5', '2e4', 'lots', '9007199254740993'])('refuses %j', (typed) => {
    expect(parseTokenCount(typed)).toBeNull();
  });
});

describe('usageOfStep', () => {
  it('is complete when it has a cost, or used nothing', () => {
    expect(usageOfStep({ input_tokens: 10, output_tokens: 5, cost_usd: 0.01 }).cost_complete).toBe(
      true,
    );
    expect(usageOfStep({ input_tokens: 0, output_tokens: 0, cost_usd: null }).cost_complete).toBe(
      true,
    );
  });

  it('is incomplete when tokens were used at an unknown cost', () => {
    const step = usageOfStep({ input_tokens: 10, output_tokens: 5, cost_usd: null });
    expect(step).toEqual({
      input_tokens: 10,
      output_tokens: 5,
      cost_usd: null,
      cost_complete: false,
    });
  });
});

describe('describeCost', () => {
  it('words a known cost, with the tokens as its tip', () => {
    expect(describeCost(usage())).toEqual({
      text: '$0.0123',
      short: '$0.0123',
      tip: '1,234 tokens in, 567 out',
      exact: true,
    });
  });

  it('says so when the cost is unknown for the model, and keeps the tokens', () => {
    expect(describeCost(usage({ cost_usd: null, cost_complete: false }))).toEqual({
      text: UNKNOWN_COST,
      short: 'Cost unknown',
      tip: '1,234 tokens in, 567 out',
      exact: false,
    });
    expect(UNKNOWN_COST).toBe('Cost unknown for this model');
  });

  it('calls a partly known cost a floor and explains why', () => {
    const view = describeCost(usage({ cost_complete: false }));

    expect(view?.text).toBe('$0.0123 or more');
    expect(view?.short).toBe('$0.0123+');
    expect(view?.tip).toContain('1,234 tokens in, 567 out.');
    expect(view?.tip).toContain('cost is unknown');
    expect(view?.exact).toBe(false);
  });

  it('has nothing to say before anything was used', () => {
    expect(
      describeCost({ input_tokens: 0, output_tokens: 0, cost_usd: null, cost_complete: true }),
    ).toBeNull();
  });

  it('still shows a known zero cost, as a free model reports it', () => {
    const view = describeCost(usage({ cost_usd: 0 }));
    expect(view?.text).toBe('$0.00');
  });
});
