import { KeyRound, Layers, MessageSquare, Plug, Sparkles, Workflow } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { DOCUMENT_KINDS } from '../../../core/api/documents';

/** Landing content that explains the product: hero steps, numbers, features, process. */

export type HeroStepId = 'describe' | 'orchestrate' | 'act' | 'review';

export interface HeroStep {
  id: HeroStepId;
  label: string;
  detail: string;
}

export const HERO_STEPS: readonly HeroStep[] = [
  {
    id: 'describe',
    label: 'Describe',
    detail: 'Write a goal in one sentence. The planner drafts inputs, stages, roles and models.',
  },
  {
    id: 'orchestrate',
    label: 'Orchestrate',
    detail: 'Agents in a stage run in parallel; their ordered results feed the next stage.',
  },
  {
    id: 'act',
    label: 'Act',
    detail: 'Give each agent a tool policy: research, calculation, your files, artifacts or MCP.',
  },
  {
    id: 'review',
    label: 'Review',
    detail: 'Read every deliverable next to its tool-call trace, tweak a step, run it again.',
  },
];

export interface Stat {
  value: number;
  label: string;
  detail: string;
}

export const STATS: readonly Stat[] = [
  { value: 3, label: 'workspaces', detail: 'Chat, Pipeline Builder and Auto Pipeline' },
  { value: 9, label: 'toolbox functions', detail: 'plus any MCP server you connect' },
  { value: 3, label: 'model providers', detail: 'OpenRouter, TogetherAI and Meta' },
];

export interface Feature {
  title: string;
  detail: string;
  icon: LucideIcon;
}

export const PLATFORM_FEATURES: readonly Feature[] = [
  {
    title: 'Chat with any model',
    detail:
      'Stream answers from your configured provider. The chat agent can inspect and run your saved pipelines.',
    icon: MessageSquare,
  },
  {
    title: 'Parallel stages',
    detail:
      'Group agents into stages. Agents in a stage run concurrently and hand ordered results to the next one.',
    icon: Layers,
  },
  {
    title: 'Named run inputs',
    detail: `Declare inputs like {topic} once, then reuse the same pipeline on every run, with each value typed or read from a ${DOCUMENT_KINDS} file.`,
    icon: Workflow,
  },
  {
    title: 'A tool policy per agent',
    detail: 'Choose exactly which tools each agent may call, built-in or from your MCP servers.',
    icon: Plug,
  },
  {
    title: 'Plan from a sentence',
    detail:
      'Describe a goal and the planner drafts stages, roles, models and expected outputs. Nothing is saved until you approve.',
    icon: Sparkles,
  },
  {
    title: 'Bring your own keys',
    detail:
      'Add your OpenRouter, TogetherAI or Meta key in Settings. It is encrypted at rest and never shown again.',
    icon: KeyRound,
  },
];

export interface ProcessStep {
  title: string;
  detail: string;
  /** The live-status line a real run would show at this point. */
  status: string;
}

export const PROCESS_STEPS: readonly ProcessStep[] = [
  {
    title: 'Connect a model',
    detail: 'Paste a provider key in Settings and pick the default model your agents start from.',
    status: 'Provider connected',
  },
  {
    title: 'Design the pipeline',
    detail:
      'Add agents, give each a role, model, prompt and tool policy, then group them into stages.',
    status: 'Stage 2 of 3 · 2 agents in parallel',
  },
  {
    title: 'Run it with your inputs',
    detail:
      'Fill in the named inputs and run. Stages go in order; agents inside a stage go together.',
    status: 'Running · 3 tool calls so far',
  },
  {
    title: 'Inspect the result',
    detail: 'Read the deliverables, open the tool-call trace, adjust a step and run it again.',
    status: 'Done · 2 deliverables ready',
  },
];
