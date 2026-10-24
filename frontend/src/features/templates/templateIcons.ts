import {
  CalendarDays,
  ChartColumn,
  FileText,
  LayoutTemplate,
  ListChecks,
  Rocket,
  SearchCheck,
  Swords,
  Telescope,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

/** Card icons by template slug; presentation stays here, the catalogue on the server. */
const ICONS: Readonly<Record<string, LucideIcon>> = {
  'market-research-brief': Telescope,
  'competitor-analysis': Swords,
  'document-digest': FileText,
  'meeting-actions': ListChecks,
  'data-insights-report': ChartColumn,
  'seo-content-brief': SearchCheck,
  'content-calendar': CalendarDays,
  'product-launch-plan': Rocket,
};

/** A template's icon; one the server adds later gets a generic icon until it has its own. */
export function templateIcon(slug: string): LucideIcon {
  return ICONS[slug] ?? LayoutTemplate;
}
