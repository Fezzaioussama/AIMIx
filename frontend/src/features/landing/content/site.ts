/** Site-wide landing content: navigation, footer and the stack shown in the marquee. */

import { LEGAL_LINKS } from '../../../core/routes';

/** What stage this release is at, shown in the nav and footer. Change it here, e.g. to 'Demo'. */
export const RELEASE_STAGE = 'Beta';

export interface NavLink {
  label: string;
  /** Section id on the landing page. */
  href: `#${string}`;
}

export const NAV_LINKS: readonly NavLink[] = [
  { label: 'Platform', href: '#platform' },
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Use cases', href: '#use-cases' },
  { label: 'Tools', href: '#tools' },
  { label: 'FAQ', href: '#faq' },
];

export interface FooterLink {
  label: string;
  /** A section id on this page (`#faq`) or an app route (`/chat`). */
  href: string;
}

export interface FooterColumn {
  title: string;
  links: readonly FooterLink[];
}

export const FOOTER_COLUMNS: readonly FooterColumn[] = [
  {
    title: 'Product',
    links: [
      { label: 'Platform', href: '#platform' },
      { label: 'How it works', href: '#how-it-works' },
      { label: 'Tools', href: '#tools' },
      { label: 'FAQ', href: '#faq' },
    ],
  },
  {
    title: 'Workspace',
    links: [
      { label: 'Missions', href: '/mission' },
      { label: 'Chat', href: '/chat' },
      { label: 'Pipelines', href: '/pipeline' },
      { label: 'Auto pipeline', href: '/auto-pipeline' },
      { label: 'Settings', href: '/settings' },
    ],
  },
  {
    title: 'Legal',
    links: LEGAL_LINKS.map((link) => ({ label: link.label, href: link.path })),
  },
];

/** What AIMIx is built on — each name is a real part of the stack (README, Stack). */
export const TECH_STACK: readonly string[] = [
  'LangGraph',
  'Model Context Protocol',
  'OpenRouter',
  'TogetherAI',
  'FastAPI',
  'React 19',
  'SQLAlchemy',
  'Tailwind CSS',
  'Vite',
];
