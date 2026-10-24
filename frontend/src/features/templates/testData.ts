import type { MissionTemplate } from '../../core/api/types';

/** Shared by the template tests: a small gallery over two categories. */
export const TEMPLATES: MissionTemplate[] = [
  {
    slug: 'market-research-brief',
    title: 'Market research brief',
    category: 'Research',
    description: 'Size up a market.',
    inputs: [
      { name: 'market', label: 'Market', description: 'The market to research.' },
      { name: 'goal', label: 'Your goal', description: 'What the brief should help decide.' },
    ],
    step_count: 5,
    stage_count: 3,
  },
  {
    slug: 'competitor-analysis',
    title: 'Competitor analysis',
    category: 'Research',
    description: 'Compare your product with its rivals.',
    inputs: [
      { name: 'product', label: 'Your product', description: '' },
      { name: 'competitors', label: '', description: '' },
    ],
    step_count: 4,
    stage_count: 3,
  },
  {
    slug: 'document-digest',
    title: 'Document digest',
    category: 'Documents',
    description: 'Turn a long document into its key points.',
    inputs: [{ name: 'document', label: 'Document', description: 'Paste the text.' }],
    step_count: 1,
    stage_count: 1,
  },
];
