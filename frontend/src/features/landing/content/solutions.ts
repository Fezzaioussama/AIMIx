import {
  Calculator,
  Clock,
  Cog,
  FileSearch,
  Files,
  Globe,
  KeyRound,
  Lock,
  PenLine,
  Plug,
  Search,
  ShieldCheck,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import { DOCUMENT_KINDS } from '../../../core/api/documents';

/** Landing content about applying the product: use cases, tools, security, FAQ. */

export interface UseCase {
  title: string;
  icon: LucideIcon;
  points: readonly string[];
}

/** Illustrative workflows — what the building blocks are good for, not customer claims. */
export const USE_CASES: readonly UseCase[] = [
  {
    title: 'Research and briefings',
    icon: FileSearch,
    points: [
      'Parallel research agents search the web',
      'Fetch and read the source pages',
      'A final agent merges the findings into one brief',
    ],
  },
  {
    title: 'Content pipelines',
    icon: PenLine,
    points: [
      'Drafter, editor and fact-checker as stages',
      'Reusable {topic} and {audience} inputs',
      'An expected output set on every step',
    ],
  },
  {
    title: 'Ops and automation',
    icon: Cog,
    points: [
      'Reach internal systems through MCP servers',
      'Limit each agent to the tools it needs',
      'Review every tool call after the run',
    ],
  },
];

export interface ToolCard {
  name: string;
  detail: string;
  icon: LucideIcon;
  kind: 'Built-in' | 'MCP';
}

export const TOOLS: readonly ToolCard[] = [
  {
    name: 'Web search',
    detail: 'Query the web and get results back.',
    icon: Search,
    kind: 'Built-in',
  },
  {
    name: 'Fetch URL',
    detail: 'Download a page and read its text.',
    icon: Globe,
    kind: 'Built-in',
  },
  {
    name: 'Calculator',
    detail: 'Evaluate arithmetic exactly instead of guessing it.',
    icon: Calculator,
    kind: 'Built-in',
  },
  {
    name: 'Current date and time',
    detail: 'Give agents a reliable clock.',
    icon: Clock,
    kind: 'Built-in',
  },
  {
    name: 'Local workspace',
    detail: 'List, search and read local files, inspect CSV data, and save new artifacts safely.',
    icon: Files,
    kind: 'Built-in',
  },
  {
    name: 'Any MCP server',
    detail: 'Connect a Model Context Protocol server; its tools appear beside the built-ins.',
    icon: Plug,
    kind: 'MCP',
  },
];

export interface SecurityPoint {
  title: string;
  detail: string;
  icon: LucideIcon;
}

/** Each point is something the backend does today (encrypted keys, per-user ownership, auth). */
export const SECURITY_POINTS: readonly SecurityPoint[] = [
  {
    title: 'Your keys stay yours',
    detail:
      'Provider keys are encrypted at rest and never returned by the API, only their last characters.',
    icon: KeyRound,
  },
  {
    title: 'Pipelines are private',
    detail:
      'Every pipeline belongs to your account, and the chat agent can only see and run yours.',
    icon: ShieldCheck,
  },
  {
    title: 'Sign-in everywhere',
    detail: 'Every workspace screen requires an account, and passwords are stored hashed.',
    icon: Lock,
  },
];

export interface FaqItem {
  question: string;
  answer: string;
}

export const FAQ_ITEMS: readonly FaqItem[] = [
  {
    question: 'Which models can I use?',
    answer:
      'Any model in the OpenRouter or TogetherAI catalogue. Pick one per agent, and set a default in Settings.',
  },
  {
    question: 'Do I need my own API key?',
    answer:
      'You bring your own: add an OpenRouter or TogetherAI key in Settings. It is encrypted at rest and never shown again.',
  },
  {
    question: 'Do pipeline runs stream?',
    answer:
      'Chat streams token by token. A pipeline run returns once every stage has finished, so a long run keeps one request open. Run history and resumable checkpoints are not built yet.',
  },
  {
    question: 'Which tools can agents use?',
    answer:
      'Nine toolbox functions cover web research, calculation, time, local files, CSV data and saved artifacts, plus anything you connect over MCP. You choose the tools per agent.',
  },
  {
    question: 'Can a pipeline read my documents?',
    answer: `Yes. Attach a ${DOCUMENT_KINDS} file to any run input and AIMIx reads it into that input, where you can still edit it. Scanned pages and photos of text are read with text recognition.`,
  },
];
