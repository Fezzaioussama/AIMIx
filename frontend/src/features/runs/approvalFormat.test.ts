import { describe, expect, it } from 'vitest';

import { argumentRows, FOLD_AFTER_CHARS, formatTimeLeft, toolLabel } from './approvalFormat';

describe('toolLabel', () => {
  it('drops the integration prefix and reads the rest as words', () => {
    expect(toolLabel('crm_send_email', 'crm')).toBe('Send email');
    expect(toolLabel('hub_create-deal', 'hub')).toBe('Create deal');
  });

  it('keeps the whole name when it does not start with the source', () => {
    expect(toolLabel('save_artifact', 'AIMIx')).toBe('Save artifact');
    expect(toolLabel('docs_search', 'MCP')).toBe('Docs search');
  });

  it('falls back to the exact name when nothing is left to read', () => {
    expect(toolLabel('crm_', 'crm')).toBe('crm_');
  });
});

describe('argumentRows', () => {
  it('shows text as written and plain values as words, in the model order', () => {
    const rows = argumentRows({ to: 'ada@example.com', count: 3, urgent: false, note: null });

    expect(rows.map((row) => [row.key, row.text])).toEqual([
      ['to', 'ada@example.com'],
      ['count', '3'],
      ['urgent', 'false'],
      ['note', '(empty)'],
    ]);
    expect(rows.some((row) => row.folded)).toBe(false);
  });

  it('puts a list of plain values on one line and anything nested as JSON', () => {
    const [cc, deal] = argumentRows({ cc: ['a@x.com', 'b@x.com'], deal: { id: 4 } });

    expect(cc.text).toBe('a@x.com, b@x.com');
    expect(deal.text).toBe('{\n  "id": 4\n}');
  });

  it('folds a long value or one with many lines, keeping its start', () => {
    const [long, tall, fits] = argumentRows({
      body: `Dear Ada, ${'word '.repeat(60)}`,
      list: 'one\ntwo\nthree\nfour\nfive',
      subject: 'x'.repeat(FOLD_AFTER_CHARS),
    });

    expect(long.folded).toBe(true);
    expect(long.preview.startsWith('Dear Ada, word word')).toBe(true);
    expect(long.preview.endsWith('…')).toBe(true);
    expect(long.text.length).toBeGreaterThan(FOLD_AFTER_CHARS);
    expect(tall.folded).toBe(true);
    expect(tall.preview).toBe('one two three four five…');
    expect(fits.folded).toBe(false);
  });

  it('has no rows for a tool that takes nothing', () => {
    expect(argumentRows({})).toEqual([]);
  });
});

describe('formatTimeLeft', () => {
  it.each([
    [0, 'Time is up'],
    [-5000, 'Time is up'],
    [1, '1 s left'],
    [45_000, '45 s left'],
    [59_001, '1 min 00 s left'],
    [125_000, '2 min 05 s left'],
    [599_000, '9 min 59 s left'],
    [600_000, '10 min left'],
    [1_684_000, '29 min left'],
    [1_800_000, '30 min left'],
  ])('says %i ms as "%s"', (ms, words) => {
    expect(formatTimeLeft(ms)).toBe(words);
  });
});
