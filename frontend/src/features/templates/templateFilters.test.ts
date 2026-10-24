import { describe, expect, it } from 'vitest';

import { ALL_CATEGORIES, categoryChips, inCategory } from './templateFilters';
import { TEMPLATES } from './testData';

describe('template filters', () => {
  it('offers All, then each category once, in gallery order', () => {
    expect(categoryChips(TEMPLATES)).toEqual([ALL_CATEGORIES, 'Research', 'Documents']);
    expect(categoryChips([])).toEqual([ALL_CATEGORIES]);
  });

  it('shows every template under All, and only matching ones under a category', () => {
    expect(inCategory(TEMPLATES, ALL_CATEGORIES)).toEqual(TEMPLATES);
    expect(inCategory(TEMPLATES, 'Research').map((template) => template.slug)).toEqual([
      'market-research-brief',
      'competitor-analysis',
    ]);
  });
});
