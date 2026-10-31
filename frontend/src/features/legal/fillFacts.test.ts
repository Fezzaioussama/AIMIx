import { describe, expect, it } from 'vitest';

import { LEGAL_LINKS } from '../../core/routes';

import { LEGAL_NOTICE } from './documents/legalNotice';
import { PRIVACY_POLICY } from './documents/privacyPolicy';
import { TERMS } from './documents/terms';
import { fillFacts, missingFacts } from './fillFacts';
import { FACT_LABELS, OPERATOR, type OperatorFacts } from './operator';

const ALL_SET = Object.fromEntries(
  Object.keys(OPERATOR).map((key) => [key, `value of ${key}`]),
) as unknown as OperatorFacts;

describe('fillFacts', () => {
  it('puts each fact the operator gave in its place', () => {
    expect(fillFacts('Édité par {{name}}, {{address}}.', ALL_SET)).toBe(
      'Édité par value of name, value of address.',
    );
  });

  it('marks a missing fact visibly instead of leaving a gap', () => {
    const facts = { ...ALL_SET, contactEmail: null };
    expect(fillFacts('Écrivez à {{contactEmail}}.', facts)).toBe(
      `Écrivez à **[à compléter : ${FACT_LABELS.contactEmail}]**.`,
    );
    expect(missingFacts(facts)).toEqual(['contactEmail']);
  });

  it('refuses a placeholder that names no fact, so a typo never ships', () => {
    expect(() => fillFacts('{{nmae}}', ALL_SET)).toThrow('Unknown operator fact {{nmae}}');
  });

  it.each([LEGAL_NOTICE, PRIVACY_POLICY, TERMS])('$title names only known facts', (page) => {
    const filled = fillFacts(page.markdown, ALL_SET);
    expect(filled).not.toMatch(/\{\{|\}\}|à compléter/);
  });

  it.each([LEGAL_NOTICE, PRIVACY_POLICY, TERMS])(
    '$title links only to pages that exist',
    (page) => {
      const internal = [...page.markdown.matchAll(/\]\((\/[^)]*)\)/g)].map((match) => match[1]);
      const known: string[] = LEGAL_LINKS.map((link) => link.path);
      expect(internal.filter((path) => !known.includes(path))).toEqual([]);
    },
  );
});
