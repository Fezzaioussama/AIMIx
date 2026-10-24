import { ArrowRight, Check, FileText, RotateCcw } from 'lucide-react';
import type { ReactNode } from 'react';

import type { HeroStepId } from './content/product';

/** The four mock screens inside the hero's product window — illustrations of each step. */

const PANEL = 'space-y-4 p-5 sm:p-7';

function Label({ children }: { children: ReactNode }) {
  return (
    <p className="text-[0.7rem] font-semibold tracking-[0.16em] text-slate-400 uppercase">
      {children}
    </p>
  );
}

function Chip({ children, tone = 'sky' }: { children: ReactNode; tone?: 'sky' | 'purple' }) {
  const colors =
    tone === 'sky'
      ? 'border-sky-400/30 bg-sky-400/10 text-sky-200'
      : 'border-purple-400/30 bg-purple-400/10 text-purple-200';
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${colors}`}>
      {children}
    </span>
  );
}

function DescribePanel() {
  return (
    <div className={PANEL}>
      <Label>Your goal</Label>
      <div className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-slate-200">
        Research three competitors and draft a launch brief for our sales team
        <span
          aria-hidden="true"
          className="ml-0.5 inline-block h-4 w-0.5 translate-y-0.5 bg-sky-300 motion-safe:animate-caret"
        />
      </div>
      <Label>The planner proposes</Label>
      <div className="flex flex-wrap gap-2">
        <Chip>{'{competitor}'}</Chip>
        <Chip>{'{audience}'}</Chip>
        <Chip tone="purple">3 stages</Chip>
        <Chip tone="purple">4 agents</Chip>
        <Chip tone="purple">Review before saving</Chip>
      </div>
    </div>
  );
}

const STAGES = [
  { name: 'Stage 1', agents: ['Researcher A', 'Researcher B'] },
  { name: 'Stage 2', agents: ['Analyst'] },
  { name: 'Stage 3', agents: ['Writer'] },
] as const;

function OrchestratePanel() {
  return (
    <div className={`${PANEL} grid items-stretch gap-3 sm:grid-cols-[1fr_auto_1fr_auto_1fr]`}>
      {STAGES.map((stage, index) => (
        <div key={stage.name} className="contents">
          {index > 0 && (
            <ArrowRight
              aria-hidden="true"
              className="hidden size-5 self-center text-indigo-300 sm:block"
            />
          )}
          <div className="space-y-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
            <Label>{stage.name}</Label>
            {stage.agents.map((agent) => (
              <div
                key={agent}
                className="rounded-lg border border-indigo-400/25 bg-indigo-400/10 px-3 py-2 text-sm font-medium text-indigo-100"
              >
                {agent}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const TOOL_CALLS = [
  { call: 'web_search("competitor pricing")', result: '5 results' },
  { call: 'fetch_url("https://example.com/pricing")', result: 'page text read' },
  { call: 'calculator("1299 * 12")', result: '15588' },
  { call: 'current_datetime()', result: 'UTC timestamp' },
] as const;

function ActPanel() {
  return (
    <div className={PANEL}>
      <Label>Tool calls · Researcher A</Label>
      <ul className="space-y-2 font-mono text-[0.8rem]">
        {TOOL_CALLS.map(({ call, result }) => (
          <li
            key={call}
            className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2"
          >
            <Check aria-hidden="true" className="size-4 shrink-0 text-emerald-300" />
            <span className="min-w-0 flex-1 truncate text-slate-200">{call}</span>
            <span className="shrink-0 text-slate-400">{result}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const BAR_WIDTHS = ['w-3/4', 'w-full', 'w-11/12', 'w-2/3'] as const;

function ReviewPanel() {
  return (
    <div className={`${PANEL} sm:grid sm:grid-cols-[2fr_1fr] sm:gap-6 sm:space-y-0`}>
      <div className="space-y-3 rounded-xl border border-white/10 bg-white/[0.03] p-4">
        <p className="flex items-center gap-2 text-sm font-semibold text-slate-100">
          <FileText aria-hidden="true" className="size-4 text-sky-300" />
          launch-brief.md
        </p>
        {BAR_WIDTHS.map((width) => (
          <span
            key={width}
            aria-hidden="true"
            className={`block h-2 rounded-full bg-white/10 ${width}`}
          />
        ))}
      </div>
      <div className="mt-4 space-y-3 sm:mt-0">
        <Label>Tool trace</Label>
        <p className="text-sm text-slate-300">4 calls across 2 agents</p>
        <span className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/[0.04] px-3 py-1.5 text-xs font-semibold text-slate-200">
          <RotateCcw aria-hidden="true" className="size-3.5" />
          Run again
        </span>
      </div>
    </div>
  );
}

export const PREVIEW_PANELS: Record<HeroStepId, () => ReactNode> = {
  describe: DescribePanel,
  orchestrate: OrchestratePanel,
  act: ActPanel,
  review: ReviewPanel,
};
