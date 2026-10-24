import type { MissionTemplate } from '../../core/api/types';

/** The chip that shows every template. */
export const ALL_CATEGORIES = 'All';

/** The gallery's filter chips: "All", then each category in the order it first appears. */
export function categoryChips(templates: MissionTemplate[]): string[] {
  return [ALL_CATEGORIES, ...new Set(templates.map((template) => template.category))];
}

export function inCategory(templates: MissionTemplate[], category: string): MissionTemplate[] {
  return category === ALL_CATEGORIES
    ? templates
    : templates.filter((template) => template.category === category);
}
