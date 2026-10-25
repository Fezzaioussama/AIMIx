import { Wrench } from 'lucide-react';

import { OutputBadge } from '../pipelines/GraphNodeCard';
import { ANSWER_ACTION, Bubble } from './Bubble';
import type { ViewProps } from './messageContext';
import type { TeamMessage } from './missionMessages';
import { countOf, providesInWords, toolsInWords, type AgentBrief } from './teamBrief';

const INTROS: Record<TeamMessage['origin'], (name: string) => string> = {
  generated: (name) => `Here’s the team I put together for “${name}”.`,
  template: (name) => `Here’s the “${name}” team, ready to go.`,
  reopened: (name) => `Here’s your “${name}” team.`,
};

function AgentLine({ agent }: { agent: AgentBrief }) {
  return (
    <li className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <p className="flex flex-wrap items-center gap-2 font-semibold text-slate-50">
        {agent.name}
        {agent.deliverable && <OutputBadge />}
      </p>
      <p className="mt-0.5 text-slate-300">{agent.task}</p>
      <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
        <Wrench aria-hidden="true" className="size-3 shrink-0" />
        {toolsInWords(agent.tools)}
      </p>
    </li>
  );
}

/** The team in plain words: each agent, what it delivers and its tools, and what to provide. */
export function TeamMessageView({ message, context }: ViewProps<'team'>) {
  const { brief } = message;
  return (
    <Bubble>
      <p>
        {INTROS[message.origin](brief.name)} {countOf(brief.agents.length, 'agent')} in{' '}
        {countOf(brief.stages, 'stage')}; agents in the same stage work at the same time.
      </p>
      <ol className="mt-3 space-y-2">
        {brief.agents.map((agent) => (
          <AgentLine key={agent.order} agent={agent} />
        ))}
      </ol>
      <p className="mt-3">{providesInWords(brief)}</p>
      <p className="mt-1 text-slate-300">
        Ask for any change in your own words, or press Run it when you’re ready.
      </p>
      <button type="button" onClick={() => context.showPane('team')} className={`mt-2 ${ANSWER_ACTION}`}>
        See the team
      </button>
    </Bubble>
  );
}
