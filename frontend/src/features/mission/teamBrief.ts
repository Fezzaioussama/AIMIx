import type { Pipeline, PipelineStep } from '../../core/api/types';
import { inputLabel } from '../pipelines/pipelineInputs';
import { joinWords } from '../pipelines/revision';
import { outputOrders, stepLabel } from '../pipelines/stages';

/** Which tools an agent may use, in the three ways a step can say it (`names` for `some`). */
export interface ToolAccess {
  kind: 'all' | 'none' | 'some';
  names: string[];
}

/** One agent of the team, as the person reads it. */
export interface AgentBrief {
  order: number;
  /** Its role, else the step's title. */
  name: string;
  /** What it delivers. */
  task: string;
  tools: ToolAccess;
  /** Its result is one of the mission's deliverables. */
  deliverable: boolean;
}

/** A team in plain words: who does what, and what the person provides on each run. */
export interface TeamBrief {
  name: string;
  agents: AgentBrief[];
  stages: number;
  /** The run's named inputs, by label; empty means one free-text description. */
  provides: string[];
}

/** Longest stretch of a prompt used to say what an agent does, when nothing shorter says it. */
const PROMPT_EXCERPT_CHARS = 140;

/** `null` grants every tool and `[]` none (the step contract). */
function toolAccess(allowed: string[] | null): ToolAccess {
  if (allowed === null) return { kind: 'all', names: [] };
  return { kind: allowed.length === 0 ? 'none' : 'some', names: allowed };
}

/** Its expected output, else its title (when the role names it), else its prompt's start. */
function taskOf(step: PipelineStep): string {
  const expected = step.expected_output.trim();
  if (expected) return expected;
  if (step.role.trim() && step.title.trim()) return step.title.trim();
  const prompt = step.prompt.trim().replace(/\s+/g, ' ');
  if (!prompt) return 'Works on what the previous agents hand over.';
  return prompt.length > PROMPT_EXCERPT_CHARS ? `${prompt.slice(0, PROMPT_EXCERPT_CHARS)}…` : prompt;
}

/** The team as AIMIx describes it: kept pure, so the conversation stores plain data. */
export function describeTeam(pipeline: Pipeline): TeamBrief {
  const deliverables = outputOrders(pipeline.steps);
  return {
    name: pipeline.name,
    agents: pipeline.steps.map((step) => ({
      order: step.order,
      name: step.role.trim() || stepLabel(step),
      task: taskOf(step),
      tools: toolAccess(step.allowed_tools),
      deliverable: deliverables.has(step.order),
    })),
    stages: new Set(pipeline.steps.map((step) => step.stage)).size,
    provides: pipeline.inputs.map(inputLabel),
  };
}

/** A tool's name as words: "web_search" → "web search". */
function toolWords(name: string): string {
  return name.replace(/_/g, ' ');
}

const ACCESS_WORDS: Record<ToolAccess['kind'], (names: string[]) => string> = {
  all: () => 'Can use any of your tools',
  none: () => 'Works without tools',
  some: (names) => `Uses ${joinWords(names.map(toolWords))}`,
};

/** "Uses web search and calculator", "Works without tools", … */
export function toolsInWords(tools: ToolAccess): string {
  return ACCESS_WORDS[tools.kind](tools.names);
}

export function countOf(amount: number, noun: string): string {
  return `${amount} ${noun}${amount === 1 ? '' : 's'}`;
}

/** What the person provides on each run, as one sentence. */
export function providesInWords(brief: TeamBrief): string {
  return brief.provides.length > 0
    ? `You provide: ${joinWords(brief.provides)}.`
    : 'You provide: a short description of what to work on.';
}
